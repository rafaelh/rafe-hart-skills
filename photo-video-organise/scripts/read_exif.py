# /// script
# requires-python = ">=3.11"
# dependencies = ["pyexiftool>=0.5"]
# ///
"""Batch EXIF reader. Outputs JSONL on stdout, one line per input path.

Usage:
    uv run read_exif.py /a.jpg /b.cr2
    uv run read_exif.py --paths-file paths.txt
    uv run read_exif.py --fields default --paths-file paths.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, TextIO


DEFAULT_FIELDS = [
    # Date
    "Composite:DateTimeOriginal",
    "EXIF:DateTimeOriginal",
    "EXIF:CreateDate",
    "QuickTime:CreateDate",
    "XMP:CreateDate",
    "File:FileModifyDate",
    # Camera
    "EXIF:Make",
    "EXIF:Model",
    "EXIF:LensModel",
    "EXIF:ISO",
    # Image
    "File:FileType",
    "File:FileSize",
    "File:MIMEType",
    "EXIF:ImageWidth",
    "EXIF:ImageHeight",
    # Video
    "QuickTime:Duration",
    "QuickTime:VideoFrameRate",
    # Location
    "Composite:GPSLatitude",
    "Composite:GPSLongitude",
    "Composite:GPSAltitude",
]


def parse_fields_arg(value: str) -> list[str]:
    if value == "default":
        return list(DEFAULT_FIELDS)
    if value == "all":
        return []  # empty = exiftool returns all tags
    return [s.strip() for s in value.split(",") if s.strip()]


def main(
    argv: list[str],
    *,
    reader_factory: Callable[[], Any],
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="read_exif")
    parser.add_argument("paths", nargs="*", help="File paths to read EXIF from")
    parser.add_argument("--paths-file", help="File with one path per line (use instead of args)")
    parser.add_argument("--fields", default="default", help="'default', 'all', or comma-separated tag list")
    args = parser.parse_args(argv)

    output = out if out is not None else sys.stdout
    error = err if err is not None else sys.stderr

    paths = list(args.paths)
    if args.paths_file:
        paths.extend(_read_paths_file(args.paths_file))

    if not paths:
        print("No paths provided.", file=error)
        return 2

    fields = parse_fields_arg(args.fields)

    ok_count = 0
    err_count = 0
    with reader_factory() as reader:
        for record in reader.read(paths, fields):
            output.write(json.dumps(record) + "\n")
            output.flush()
            if record.get("ok"):
                ok_count += 1
            else:
                err_count += 1

    print(f"Read EXIF for {len(paths)} paths: {ok_count} ok, {err_count} errors.", file=error)
    return 0


def _read_paths_file(path: str) -> list[str]:
    return [line.rstrip("\n") for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    SCRIPTS_DIR = Path(__file__).resolve().parent
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from lib.exif import ExifReader  # noqa: E402, PLC0415

    sys.exit(main(sys.argv[1:], reader_factory=lambda: ExifReader()))
