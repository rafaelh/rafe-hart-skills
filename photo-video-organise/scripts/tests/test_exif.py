from lib.exif import ExifReader


class FakeHelper:
    """Stand-in for exiftool.ExifToolHelper for unit tests."""

    def __init__(self, *, responses=None, raises_for=None):
        self.responses = responses or {}
        self.raises_for = raises_for or {}
        self.calls = []

    def get_tags(self, paths, tags=None, params=None):
        self.calls.append({"paths": list(paths), "tags": list(tags) if tags else None})
        result = []
        for p in paths:
            if p in self.raises_for:
                raise self.raises_for[p]
            row = {"SourceFile": p, **self.responses.get(p, {})}
            result.append(row)
        return result


class TestExifReaderRead:
    def test_returns_per_file_results_in_input_order(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"fake-jpeg")
        b.write_bytes(b"fake-jpeg")
        helper = FakeHelper(
            responses={
                str(a): {"EXIF:DateTimeOriginal": "2019:08:15 14:20:30"},
                str(b): {"EXIF:DateTimeOriginal": "2020:01:01 00:00:00"},
            }
        )
        reader = ExifReader(helper=helper)
        results = reader.read(paths=[str(a), str(b)], fields=["EXIF:DateTimeOriginal"])
        assert [r["path"] for r in results] == [str(a), str(b)]
        assert all(r["ok"] for r in results)
        assert results[0]["fields"]["EXIF:DateTimeOriginal"] == "2019:08:15 14:20:30"

    def test_missing_file_marked_not_ok(self, tmp_path):
        existing = tmp_path / "a.jpg"
        existing.write_bytes(b"fake-jpeg")
        missing = tmp_path / "ghost.jpg"
        helper = FakeHelper(responses={str(existing): {"X": "y"}})
        reader = ExifReader(helper=helper)
        results = reader.read(paths=[str(existing), str(missing)], fields=["X"])
        assert results[0]["ok"] is True
        assert results[1]["ok"] is False
        assert results[1]["error"] == "file_not_found"
        # exiftool was only asked about the existing file
        assert helper.calls[0]["paths"] == [str(existing)]

    def test_per_file_exiftool_error_field_propagates(self, tmp_path):
        bad = tmp_path / "corrupt.jpg"
        bad.write_bytes(b"not a real jpeg")
        helper = FakeHelper(responses={str(bad): {"Error": "Unknown file type"}})
        reader = ExifReader(helper=helper)
        [result] = reader.read(paths=[str(bad)], fields=["X"])
        assert result["ok"] is False
        assert result["error"] == "exiftool_error"
        assert "Unknown file type" in result["exiftool_message"]
