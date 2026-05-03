import io
import json

from inventory import chunk_inventory, classify_format, main, scan_inventory


class TestScanInventory:
    def test_yields_one_entry_per_file(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"x" * 100)
        (tmp_path / "b.cr2").write_bytes(b"y" * 200)
        entries = list(scan_inventory(tmp_path))
        paths = sorted(e["path"] for e in entries)
        assert paths == [str(tmp_path / "a.jpg"), str(tmp_path / "b.cr2")]

    def test_records_size_and_extension(self, tmp_path):
        (tmp_path / "photo.JPG").write_bytes(b"x" * 1234)
        [entry] = list(scan_inventory(tmp_path))
        assert entry["size"] == 1234
        assert entry["ext"] == ".jpg"  # normalized lowercase

    def test_recursive_into_subdirs(self, tmp_path):
        (tmp_path / "outer.jpg").write_bytes(b"x")
        sub = tmp_path / "2019" / "Aug"
        sub.mkdir(parents=True)
        (sub / "inner.cr2").write_bytes(b"x")
        paths = sorted(e["path"] for e in scan_inventory(tmp_path))
        assert paths == [str(tmp_path / "2019" / "Aug" / "inner.cr2"), str(tmp_path / "outer.jpg")]

    def test_skips_directories_themselves(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "f.jpg").write_bytes(b"x")
        entries = list(scan_inventory(tmp_path))
        assert len(entries) == 1
        assert entries[0]["path"].endswith("f.jpg")

    def test_inventory_entries_carry_format_class(self, tmp_path):
        (tmp_path / "photo.cr2").write_bytes(b"x")
        (tmp_path / "doc.txt").write_bytes(b"x")
        (tmp_path / "archive.zip").write_bytes(b"x")
        by_path = {e["path"]: e for e in scan_inventory(tmp_path)}
        assert by_path[str(tmp_path / "photo.cr2")]["format_class"] == "first_class"
        assert by_path[str(tmp_path / "doc.txt")]["format_class"] == "best_effort"
        assert by_path[str(tmp_path / "archive.zip")]["format_class"] == "excluded"


class TestClassifyFormat:
    def test_first_class_extensions(self):
        for ext in [".jpg", ".jpeg", ".png", ".cr2", ".cr3", ".mp4", ".mov", ".m4v", ".avi", ".tif", ".tiff", ".heic", ".xmp"]:
            assert classify_format(ext) == "first_class", ext

    def test_excluded_extensions(self):
        for ext in [".zip", ".tar", ".rar", ".7z", ".psd", ".lrcat", ".db", ".sqlite"]:
            assert classify_format(ext) == "excluded", ext

    def test_unrecognized_is_best_effort(self):
        assert classify_format(".txt") == "best_effort"
        assert classify_format(".bmp") == "best_effort"

    def test_extension_case_normalized(self):
        assert classify_format(".JPG") == "first_class"
        assert classify_format(".ZIP") == "excluded"


class TestChunkInventory:
    def _entry(self, path):
        return {"path": path, "size": 0, "mtime": 0, "ext": ".jpg", "format_class": "first_class"}

    def test_files_in_distinct_folders_become_separate_chunks(self):
        entries = [
            self._entry("/root/A/1.jpg"),
            self._entry("/root/A/2.jpg"),
            self._entry("/root/B/3.jpg"),
        ]
        chunks = list(chunk_inventory(entries, root="/root", max_per_chunk=10))
        names = [c["name"] for c in chunks]
        assert sorted(names) == ["A", "B"]
        a = next(c for c in chunks if c["name"] == "A")
        assert len(a["entries"]) == 2

    def test_oversized_folder_splits_into_multiple_chunks(self):
        entries = [self._entry(f"/root/A/{i}.jpg") for i in range(1200)]
        chunks = list(chunk_inventory(entries, root="/root", max_per_chunk=500))
        assert len(chunks) == 3
        # Names disambiguate parts of the same folder
        assert all(c["name"].startswith("A") for c in chunks)
        assert sum(len(c["entries"]) for c in chunks) == 1200

    def test_root_files_grouped_under_root_name(self):
        entries = [self._entry("/root/x.jpg"), self._entry("/root/y.jpg")]
        chunks = list(chunk_inventory(entries, root="/root", max_per_chunk=500))
        assert len(chunks) == 1
        assert chunks[0]["name"] == "."


class TestInventoryCli:
    def test_outputs_jsonl_to_stdout(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"x")
        (tmp_path / "b.cr2").write_bytes(b"y")
        out = io.StringIO()
        err = io.StringIO()
        rc = main([str(tmp_path)], out=out, err=err)
        assert rc == 0
        lines = [ln for ln in out.getvalue().split("\n") if ln.strip()]
        assert len(lines) == 2
        records = [json.loads(ln) for ln in lines]
        assert {r["ext"] for r in records} == {".jpg", ".cr2"}

    def test_summary_on_stderr_includes_counts(self, tmp_path):
        (tmp_path / "a.jpg").write_bytes(b"x")
        (tmp_path / "b.cr2").write_bytes(b"y")
        (tmp_path / "junk.zip").write_bytes(b"z")
        err = io.StringIO()
        rc = main([str(tmp_path)], out=io.StringIO(), err=err)
        assert rc == 0
        message = err.getvalue()
        assert "3" in message  # total
        assert "first_class" in message
        assert "excluded" in message
