# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Walk a source tree and emit a per-file inventory."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterator
from os import PathLike
from pathlib import Path
from typing import Any, TextIO


FIRST_CLASS_EXTENSIONS = frozenset({
    ".jpg", ".jpeg", ".png",
    ".cr2", ".cr3", ".nef", ".arw",
    ".mp4", ".mov", ".m4v", ".avi",
    ".tif", ".tiff",
    ".heic", ".heif",
    ".xmp",
})

EXCLUDED_EXTENSIONS = frozenset({
    ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
    ".psd", ".psb",
    ".lrcat", ".lrdata",
    ".db", ".sqlite", ".sqlite3",
})


def classify_format(ext: str) -> str:
    e = ext.lower()
    if e in FIRST_CLASS_EXTENSIONS:
        return "first_class"
    if e in EXCLUDED_EXTENSIONS:
        return "excluded"
    return "best_effort"


def chunk_inventory(
    entries: Iterator[dict[str, Any]] | list[dict[str, Any]],
    *,
    root: str | PathLike[str],
    max_per_chunk: int,
) -> Iterator[dict[str, Any]]:
    root_path = Path(root)
    by_folder: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        rel = Path(entry["path"]).parent.relative_to(root_path)
        key = str(rel) if str(rel) else "."
        by_folder.setdefault(key, []).append(entry)

    for folder in sorted(by_folder):
        files = by_folder[folder]
        if len(files) <= max_per_chunk:
            yield {"name": folder, "entries": files}
            continue
        # Split into part_001, part_002, ...
        for i, start in enumerate(range(0, len(files), max_per_chunk), start=1):
            yield {
                "name": f"{folder}#part_{i:03d}",
                "entries": files[start : start + max_per_chunk],
            }


def scan_inventory(root: str | PathLike[str]) -> Iterator[dict[str, Any]]:
    root_path = Path(root)
    for entry in sorted(root_path.rglob("*")):
        if not entry.is_file():
            continue
        stat = entry.stat()
        ext = entry.suffix.lower()
        yield {
            "path": str(entry),
            "size": stat.st_size,
            "mtime": stat.st_mtime,
            "ext": ext,
            "format_class": classify_format(ext),
        }


def main(argv: list[str], *, out: TextIO | None = None, err: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="inventory")
    parser.add_argument("root", help="Source root to scan recursively")
    args = parser.parse_args(argv)

    output = out if out is not None else sys.stdout
    error = err if err is not None else sys.stderr

    root = Path(args.root)
    if not root.exists():
        print(f"Source root does not exist: {root}", file=error)
        return 2
    if not root.is_dir():
        print(f"Source root is not a directory: {root}", file=error)
        return 2

    counts: Counter[str] = Counter()
    total = 0
    for entry in scan_inventory(root):
        output.write(json.dumps(entry) + "\n")
        counts[entry["format_class"]] += 1
        total += 1
    output.flush()

    print(f"Inventoried {total} files.", file=error)
    for cls in ("first_class", "best_effort", "excluded"):
        if counts[cls]:
            print(f"  {cls}: {counts[cls]}", file=error)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
