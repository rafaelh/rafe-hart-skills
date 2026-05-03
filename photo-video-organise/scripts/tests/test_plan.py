import io
import json

from plan import main, plan_entries


class FakeExifReader:
    def __init__(self, exif_by_path=None):
        self.exif_by_path = exif_by_path or {}
        self.queried = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def read(self, paths, fields):
        self.queried.extend(paths)
        return [
            {"path": p, "ok": True, "fields": self.exif_by_path.get(p, {})}
            for p in paths
        ]


STRATEGY_CONFIG = {
    "date_sources": ["exif:Composite:DateTimeOriginal", "mtime"],
    "path_template": "{year}/{year}-{month:02d}/",
    "format_rules": {
        "raw": {"extensions": [".cr2"], "path_template": "{year}/{year}-{month:02d}/RAW/"},
    },
}


class TestPlanEntries:
    def test_single_pair_produces_one_plan_row(self):
        entries = [
            {"path": "/src/IMG_1234.CR2", "size": 100, "mtime": 1577836800.0, "ext": ".cr2", "format_class": "first_class"},
            {"path": "/src/IMG_1234.JPG", "size": 50, "mtime": 1577836800.0, "ext": ".jpg", "format_class": "first_class"},
        ]
        reader = FakeExifReader(
            exif_by_path={"/src/IMG_1234.CR2": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"}}
        )
        rows = list(plan_entries(
            entries,
            strategy_config=STRATEGY_CONFIG,
            exif_reader=reader,
            destination_root="/dst",
        ))
        assert len(rows) == 1
        assert rows[0]["action"] == "move"
        # Both members must be in the destination_files
        assert len(rows[0]["destination_files"]) == 2

    def test_excluded_files_skipped(self):
        entries = [
            {"path": "/src/IMG_1234.CR2", "mtime": 1577836800.0, "ext": ".cr2", "format_class": "first_class"},
            {"path": "/src/junk.zip", "mtime": 1577836800.0, "ext": ".zip", "format_class": "excluded"},
        ]
        reader = FakeExifReader(
            exif_by_path={"/src/IMG_1234.CR2": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"}}
        )
        rows = list(plan_entries(entries, strategy_config=STRATEGY_CONFIG, exif_reader=reader, destination_root="/dst"))
        assert len(rows) == 1
        primary = rows[0]["primary_file"]
        assert primary == "/src/IMG_1234.CR2"

    def test_exif_only_queried_for_first_class_primaries(self):
        entries = [
            {"path": "/src/IMG_1234.CR2", "mtime": 1577836800.0, "ext": ".cr2", "format_class": "first_class"},
            {"path": "/src/random.bmp", "mtime": 1577836800.0, "ext": ".bmp", "format_class": "best_effort"},
        ]
        reader = FakeExifReader(exif_by_path={"/src/IMG_1234.CR2": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"}})
        list(plan_entries(entries, strategy_config=STRATEGY_CONFIG, exif_reader=reader, destination_root="/dst"))
        # Only the first_class file got an exiftool query.
        assert reader.queried == ["/src/IMG_1234.CR2"]


class TestMainCli:
    def test_emits_jsonl_to_stdout(self, tmp_path):
        # Set up strategy.json
        strategy_path = tmp_path / "strategy.json"
        strategy_path.write_text(json.dumps({**STRATEGY_CONFIG, "destination_root": "/dst"}))
        # Set up inventory.jsonl
        inv_path = tmp_path / "inventory.jsonl"
        inv_lines = [
            json.dumps({"path": "/src/IMG_1234.CR2", "mtime": 1577836800.0, "ext": ".cr2", "format_class": "first_class"}),
            json.dumps({"path": "/src/IMG_1234.JPG", "mtime": 1577836800.0, "ext": ".jpg", "format_class": "first_class"}),
        ]
        inv_path.write_text("\n".join(inv_lines) + "\n")

        reader = FakeExifReader(
            exif_by_path={"/src/IMG_1234.CR2": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"}}
        )
        out = io.StringIO()
        rc = main(
            [
                "--strategy", str(strategy_path),
                "--inventory", str(inv_path),
                "--destination", "/dst",
            ],
            exif_reader_factory=lambda: reader,
            out=out,
            err=io.StringIO(),
        )
        assert rc == 0
        lines = [ln for ln in out.getvalue().split("\n") if ln.strip()]
        assert len(lines) == 1
        row = json.loads(lines[0])
        assert row["action"] == "move"

    def test_sample_limits_rows(self, tmp_path):
        strategy_path = tmp_path / "strategy.json"
        strategy_path.write_text(json.dumps(STRATEGY_CONFIG))
        inv_path = tmp_path / "inventory.jsonl"
        # Three independent groups
        inv_lines = [
            json.dumps({"path": f"/src/{stem}.JPG", "mtime": 1577836800.0, "ext": ".jpg", "format_class": "first_class"})
            for stem in ("A", "B", "C")
        ]
        inv_path.write_text("\n".join(inv_lines) + "\n")

        reader = FakeExifReader(
            exif_by_path={
                f"/src/{s}.JPG": {"Composite:DateTimeOriginal": "2019:08:15 14:20:30"} for s in ("A", "B", "C")
            }
        )
        out = io.StringIO()
        rc = main(
            [
                "--strategy", str(strategy_path),
                "--inventory", str(inv_path),
                "--destination", "/dst",
                "--sample", "2",
            ],
            exif_reader_factory=lambda: reader,
            out=out,
            err=io.StringIO(),
        )
        assert rc == 0
        lines = [ln for ln in out.getvalue().split("\n") if ln.strip()]
        assert len(lines) == 2
