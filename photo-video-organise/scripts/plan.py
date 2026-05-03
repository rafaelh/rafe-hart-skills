# /// script
# requires-python = ">=3.11"
# dependencies = ["pyexiftool>=0.5"]
# ///
"""Planner: turn an inventory + strategy into plan.jsonl rows."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Iterable, Iterator
from itertools import islice
from os import PathLike
from pathlib import Path
from typing import Any, TextIO

from lib.pairing import group_pairs
from lib.strategy import Strategy

# Default extensions that are eligible for stem-based pairing.
DEFAULT_PAIR_EXTENSIONS = frozenset({
    ".cr2", ".cr3", ".jpg", ".jpeg", ".heic", ".heif",
    ".mov", ".mp4", ".m4v", ".tif", ".tiff", ".xmp",
})


def plan_entries(
    entries: Iterable[dict[str, Any]],
    *,
    strategy_config: dict[str, Any],
    exif_reader: Any,
    destination_root: str | PathLike[str],
) -> Iterator[dict[str, Any]]:
    """Yield plan rows for the given inventory entries.

    `exif_reader` must support context manager + `.read(paths, fields)`.
    Excluded entries are skipped (never planned).
    """
    strategy = Strategy(strategy_config)
    pair_exts = frozenset(strategy_config.get("pair_extensions", DEFAULT_PAIR_EXTENSIONS))

    eligible = [e for e in entries if e.get("format_class") != "excluded"]
    groups = group_pairs(eligible, pair_extensions=pair_exts)

    # EXIF only for first-class primary files (best-effort/unknowns get filename/mtime).
    exif_paths = [
        g["primary"]["path"]
        for g in groups
        if g["primary"].get("format_class") == "first_class"
    ]

    exif_by_path: dict[str, dict[str, Any]] = {}
    if exif_paths:
        with exif_reader as r:
            # Field selection: ask for the strategy's date sources (the EXIF ones, anyway).
            requested_fields = [
                src.split(":", 1)[1]
                for src in strategy_config.get("date_sources", [])
                if src.startswith("exif:")
            ]
            for record in r.read(exif_paths, requested_fields):
                if record.get("ok"):
                    exif_by_path[record["path"]] = record.get("fields", {})

    for group in groups:
        yield strategy.plan_group(group, exif_by_path=exif_by_path, destination_root=destination_root)


def main(
    argv: list[str],
    *,
    exif_reader_factory: Callable[[], Any] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="plan")
    parser.add_argument("--strategy", required=True, help="Path to strategy.json")
    parser.add_argument("--inventory", required=True, help="Path to inventory.jsonl")
    parser.add_argument("--destination", required=True, help="Destination root directory")
    parser.add_argument("--sample", type=int, help="Emit only the first N plan rows")
    args = parser.parse_args(argv)

    output = out if out is not None else sys.stdout
    error = err if err is not None else sys.stderr

    strategy_config = json.loads(Path(args.strategy).read_text(encoding="utf-8"))
    inventory = [
        json.loads(line)
        for line in Path(args.inventory).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    factory = exif_reader_factory or _default_reader_factory
    rows = plan_entries(
        inventory,
        strategy_config=strategy_config,
        exif_reader=factory(),
        destination_root=args.destination,
    )
    if args.sample:
        rows = islice(rows, args.sample)

    count = 0
    for row in rows:
        output.write(json.dumps(row) + "\n")
        count += 1
    output.flush()

    print(f"Planned {count} groups.", file=error)
    return 0


def _default_reader_factory() -> Any:
    from lib.exif import ExifReader  # noqa: PLC0415

    return ExifReader()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
