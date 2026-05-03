import io
import json

from read_exif import main, parse_fields_arg


class FakeReader:
    """Stand-in for lib.exif.ExifReader used as a context manager."""

    def __init__(self, results_by_call=None):
        self.results_by_call = results_by_call or []
        self.calls = []
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, *a):
        self.exited = True

    def read(self, paths, fields):
        self.calls.append({"paths": list(paths), "fields": list(fields)})
        if self.results_by_call:
            return self.results_by_call.pop(0)
        return [{"path": p, "ok": True, "fields": {}} for p in paths]


class TestParseFieldsArg:
    def test_default_returns_curated_list(self):
        fields = parse_fields_arg("default")
        assert "Composite:DateTimeOriginal" in fields
        assert "EXIF:Model" in fields
        assert len(fields) > 5

    def test_all_returns_empty_list(self):
        # Empty list signals "all tags" to exiftool
        assert parse_fields_arg("all") == []

    def test_comma_separated_explicit_list(self):
        assert parse_fields_arg("a,b,c") == ["a", "b", "c"]

    def test_strips_whitespace(self):
        assert parse_fields_arg(" a , b , c ") == ["a", "b", "c"]


class TestMainArgsMode:
    def test_outputs_one_jsonl_line_per_path(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        reader = FakeReader(
            results_by_call=[
                [
                    {"path": str(a), "ok": True, "fields": {"X": "1"}},
                    {"path": str(b), "ok": True, "fields": {"X": "2"}},
                ]
            ]
        )
        out = io.StringIO()
        rc = main([str(a), str(b)], reader_factory=lambda: reader, out=out, err=io.StringIO())
        assert rc == 0
        lines = out.getvalue().strip().split("\n")
        assert len(lines) == 2
        rec0 = json.loads(lines[0])
        assert rec0["path"] == str(a)
        assert rec0["ok"] is True
        assert rec0["fields"]["X"] == "1"


class TestMainPathsFileMode:
    def test_reads_paths_from_file(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"x")
        b.write_bytes(b"x")
        listfile = tmp_path / "paths.txt"
        listfile.write_text(f"{a}\n{b}\n")
        reader = FakeReader()
        out = io.StringIO()
        rc = main(
            ["--paths-file", str(listfile)],
            reader_factory=lambda: reader,
            out=out,
            err=io.StringIO(),
        )
        assert rc == 0
        assert reader.calls[0]["paths"] == [str(a), str(b)]


class TestMainNoPaths:
    def test_returns_nonzero_with_helpful_message(self):
        out = io.StringIO()
        err = io.StringIO()
        rc = main([], reader_factory=lambda: FakeReader(), out=out, err=err)
        assert rc != 0
        assert "no paths" in err.getvalue().lower()
