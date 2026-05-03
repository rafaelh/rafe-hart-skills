# /// script
# requires-python = ">=3.11"
# dependencies = ["platformdirs>=4"]
# ///
"""List, inspect, and purge job state directories."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from os import PathLike
from pathlib import Path
from typing import Any, TextIO

from lib.journal import JobJournal


def list_jobs(jobs_root: str | PathLike[str]) -> list[dict[str, Any]]:
    root = Path(jobs_root)
    if not root.exists():
        return []
    results = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        journal = JobJournal(child)
        results.append({
            "job_id": child.name,
            "path": str(child),
            "in_progress": journal.is_in_progress,
            "status": journal.read_status(),
        })
    return results


def purge_job(jobs_root: str | PathLike[str], job_id: str) -> None:
    target = Path(jobs_root) / job_id
    if target.exists():
        shutil.rmtree(target)


def _resolve_jobs_root() -> Path:
    import platformdirs  # noqa: PLC0415

    return Path(platformdirs.user_state_dir("photo-organise")) / "jobs"


def main(argv: list[str], *, out: TextIO | None = None, err: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jobs")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List all jobs")
    show = sub.add_parser("show", help="Show details of a single job")
    show.add_argument("job_id")
    purge = sub.add_parser("purge", help="Delete a job's state directory")
    purge.add_argument("job_id")
    args = parser.parse_args(argv)

    output = out if out is not None else sys.stdout
    error = err if err is not None else sys.stderr
    jobs_root = _resolve_jobs_root()

    if args.cmd == "list":
        for entry in list_jobs(jobs_root):
            output.write(json.dumps(entry) + "\n")
        return 0

    if args.cmd == "show":
        target = jobs_root / args.job_id
        if not target.exists():
            print(f"No job: {args.job_id}", file=error)
            return 1
        journal = JobJournal(target)
        info = {
            "job_id": args.job_id,
            "path": str(target),
            "in_progress": journal.is_in_progress,
            "status": journal.read_status(),
            "progress_records": list(journal.iter_progress()),
        }
        output.write(json.dumps(info, indent=2) + "\n")
        return 0

    if args.cmd == "purge":
        purge_job(jobs_root, args.job_id)
        print(f"Purged {args.job_id}.", file=error)
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
