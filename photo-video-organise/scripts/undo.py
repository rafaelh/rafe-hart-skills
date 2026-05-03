# /// script
# requires-python = ">=3.11"
# dependencies = ["platformdirs>=4"]
# ///
"""Reverse a job's moves by reading its journal."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import TextIO

from lib.journal import JobJournal


def undo_job(*, journal: JobJournal) -> dict[str, int]:
    restored = 0
    skipped = 0
    failed = 0
    for record in journal.iter_progress():
        if record.get("status") not in ("moved", "quarantined:duplicate", "quarantined:conflict"):
            continue
        for entry in record.get("destination_files", []):
            src = Path(entry["src"])
            dst = Path(entry["dst"])
            if not dst.exists():
                skipped += 1
                continue
            if src.exists():
                # Source slot is now occupied — skip rather than clobber.
                skipped += 1
                continue
            try:
                src.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dst), str(src))
                restored += 1
            except OSError:
                failed += 1
    return {"restored": restored, "skipped": skipped, "failed": failed}


def main(argv: list[str], *, out: TextIO | None = None, err: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="undo")
    parser.add_argument("job_id", help="Job id to undo")
    args = parser.parse_args(argv)

    output = out if out is not None else sys.stdout
    error = err if err is not None else sys.stderr

    import platformdirs  # noqa: PLC0415
    state_dir = Path(platformdirs.user_state_dir("photo-organise")) / "jobs" / args.job_id
    if not state_dir.exists():
        print(f"No job found at {state_dir}", file=error)
        return 1

    journal = JobJournal(state_dir)
    result = undo_job(journal=journal)
    output.write(json.dumps(result) + "\n")
    output.flush()
    print(f"Restored: {result['restored']}, skipped: {result['skipped']}, failed: {result['failed']}.", file=error)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
