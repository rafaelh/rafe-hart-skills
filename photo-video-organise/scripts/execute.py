# /// script
# requires-python = ">=3.11"
# dependencies = ["platformdirs>=4"]
# ///
"""Execute a plan.jsonl, moving files atomically per group.

Same-volume moves use os.replace (atomic rename). Cross-volume moves use
copy + SHA256 verify + delete to avoid silent corruption.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from lib.conflict import classify_collision, compute_full_hash
from lib.journal import JobJournal
from lib.platform import is_same_volume

RETRYABLE_ERRORS = (PermissionError, BlockingIOError)


def move_with_retry(
    move_fn: Callable[[str, str], Any],
    src: str,
    dst: str,
    *,
    attempts: int,
    backoff: float,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> None:
    """Call move_fn(src, dst). Retry on retryable errors with exponential backoff.

    Sleeps only between attempts, never after the final failure.
    """
    delay = backoff
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            move_fn(src, dst)
            return
        except RETRYABLE_ERRORS as e:
            last_error = e
            if attempt < attempts - 1:
                sleep_fn(delay)
                delay *= 2
    if last_error is not None:
        raise last_error


def execute_plan(
    plan: Iterable[dict[str, Any]],
    *,
    journal: JobJournal,
    source_root: str | os.PathLike[str] | None = None,
    to_delete_root: str | os.PathLike[str] | None = None,
    conflicts_root: str | os.PathLike[str] | None = None,
) -> dict[str, int]:
    done = 0
    failed = 0
    skipped = 0
    duplicates = 0
    conflicts = 0
    plan_list = list(plan)  # so we can compute total
    journal.mark_in_progress()
    try:
        for row in plan_list:
            action = row.get("action", "move")
            if action.startswith("skip:"):
                journal.append_progress({
                    "primary_file": row["primary_file"],
                    "status": "skipped",
                    "reason": action,
                })
                skipped += 1
                continue

            collision = _classify_group_collision(row)
            effective_row = row
            effective_status = "moved"
            if collision == "duplicate" and to_delete_root and source_root:
                effective_row = _reroute_group(row, source_root=source_root, target_root=to_delete_root)
                effective_status = "quarantined:duplicate"
            elif collision == "conflict" and conflicts_root and source_root:
                effective_row = _reroute_group(row, source_root=source_root, target_root=conflicts_root)
                effective_status = "quarantined:conflict"

            try:
                _execute_group(effective_row)
                journal.append_progress({
                    "primary_file": row["primary_file"],
                    "status": effective_status,
                    "destination_files": effective_row["destination_files"],
                })
                if effective_status == "moved":
                    done += 1
                elif effective_status == "quarantined:duplicate":
                    duplicates += 1
                elif effective_status == "quarantined:conflict":
                    conflicts += 1
            except Exception as e:
                journal.append_progress({
                    "primary_file": row["primary_file"],
                    "status": "failed",
                    "error": str(e),
                })
                failed += 1
    finally:
        journal.clear_in_progress()
    final = {
        "done": done,
        "failed": failed,
        "skipped": skipped,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "total": len(plan_list),
    }
    journal.write_status(final)
    return final


def _classify_group_collision(row: dict[str, Any]) -> str:
    """Classify a group's collision status by inspecting the primary file's dst.

    Returns one of: "clear", "duplicate", "conflict".
    """
    primary_path = row["primary_file"]
    primary_dst = next(
        (d["dst"] for d in row["destination_files"] if d["src"] == primary_path),
        None,
    )
    if primary_dst is None:
        return "clear"
    return classify_collision(primary_path, primary_dst)


def _reroute_group(
    row: dict[str, Any],
    *,
    source_root: str | os.PathLike[str],
    target_root: str | os.PathLike[str],
) -> dict[str, Any]:
    """Return a copy of the row with destinations rewritten under target_root,
    preserving the source-relative folder structure.
    """
    src_root_p = Path(source_root)
    tgt_root_p = Path(target_root)
    new_dests = []
    for d in row["destination_files"]:
        src = Path(d["src"])
        try:
            rel = src.relative_to(src_root_p)
        except ValueError:
            rel = Path(src.name)
        new_dests.append({"src": str(src), "dst": str(tgt_root_p / rel)})
    return {**row, "destination_files": new_dests}


def _execute_group(row: dict[str, Any], *, retry_attempts: int = 3, retry_backoff: float = 0.5) -> None:
    """Move all files in a group atomically (best-effort rollback on failure)."""
    pairs = [(Path(d["src"]), Path(d["dst"])) for d in row["destination_files"]]
    completed: list[tuple[Path, Path]] = []
    try:
        for src, dst in pairs:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if is_same_volume(src, dst.parent):
                move_with_retry(
                    lambda s, d: os.replace(s, d),
                    str(src),
                    str(dst),
                    attempts=retry_attempts,
                    backoff=retry_backoff,
                )
            else:
                move_with_retry(
                    lambda s, d: _cross_volume_copy_verify_delete(Path(s), Path(d)),
                    str(src),
                    str(dst),
                    attempts=retry_attempts,
                    backoff=retry_backoff,
                )
            completed.append((src, dst))
    except Exception:
        # Roll back: restore moved files; remove copies that landed at dst.
        for src, dst in completed:
            if dst.exists() and not src.exists():
                try:
                    shutil.move(str(dst), str(src))
                except OSError:
                    pass
        raise


def _cross_volume_copy_verify_delete(src: Path, dst: Path) -> None:
    shutil.copy2(src, dst)
    if compute_full_hash(src) != compute_full_hash(dst):
        # Verification failed — clean up the bad copy and bubble.
        try:
            dst.unlink()
        except OSError:
            pass
        raise RuntimeError(f"Hash mismatch after copy: {src} → {dst}")
    src.unlink()


def main(argv: list[str], *, out: TextIO | None = None, err: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="execute")
    parser.add_argument("--plan", required=True, help="Path to plan.jsonl")
    parser.add_argument("--source-root", required=True, help="Source root (for collision rerouting)")
    parser.add_argument("--destination-root", required=True, help="Destination root (To_Delete and _conflicts live here)")
    parser.add_argument("--job-id", help="Job id (defaults to timestamped)")
    args = parser.parse_args(argv)

    output = out if out is not None else sys.stdout
    error = err if err is not None else sys.stderr

    plan = [json.loads(line) for line in Path(args.plan).read_text(encoding="utf-8").splitlines() if line.strip()]
    job_id = args.job_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    import platformdirs  # noqa: PLC0415
    state_dir = Path(platformdirs.user_state_dir("photo-organise")) / "jobs" / job_id
    journal = JobJournal(state_dir)

    dest_root = Path(args.destination_root)
    result = execute_plan(
        plan,
        journal=journal,
        source_root=args.source_root,
        to_delete_root=dest_root / "To_Delete" / "duplicates",
        conflicts_root=dest_root / "_conflicts",
    )

    output.write(json.dumps({"job_id": job_id, **result}) + "\n")
    output.flush()
    print(f"Done: {result['done']}, failed: {result['failed']}, "
          f"skipped: {result['skipped']}, dups: {result['duplicates']}, "
          f"conflicts: {result['conflicts']}.", file=error)
    print(f"State dir: {state_dir}", file=error)
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
