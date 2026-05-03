from pathlib import PurePosixPath, PureWindowsPath

from lib.paths import to_posix, with_long_path_prefix


class TestToPosix:
    def test_windows_path_uses_forward_slashes(self):
        assert to_posix(PureWindowsPath(r"C:\Users\rhart\photo.jpg")) == "C:/Users/rhart/photo.jpg"

    def test_posix_path_passes_through(self):
        assert to_posix(PurePosixPath("/home/rafe/photo.jpg")) == "/home/rafe/photo.jpg"

    def test_string_with_backslashes_normalized(self):
        assert to_posix(r"D:\PhotoDump\IMG_1234.CR2") == "D:/PhotoDump/IMG_1234.CR2"


class TestWithLongPathPrefix:
    def test_windows_long_absolute_path_gets_prefix(self):
        long_tail = "deep" * 100  # well over the 240 char threshold
        path = rf"C:\Users\rhart\{long_tail}\photo.jpg"
        result = with_long_path_prefix(path, platform="Windows")
        assert result.startswith("\\\\?\\")
        assert "photo.jpg" in result

    def test_windows_short_path_unchanged(self):
        path = r"C:\Users\rhart\photo.jpg"
        assert with_long_path_prefix(path, platform="Windows") == path

    def test_non_windows_long_path_is_noop(self):
        long_tail = "deep" * 100
        path = f"/home/rafe/{long_tail}/photo.jpg"
        assert with_long_path_prefix(path, platform="Linux") == path
        assert with_long_path_prefix(path, platform="Darwin") == path

    def test_already_prefixed_path_not_double_prefixed(self):
        path = "\\\\?\\C:\\Users\\rhart\\" + "deep" * 100 + "\\photo.jpg"
        result = with_long_path_prefix(path, platform="Windows")
        assert result.count("\\\\?\\") == 1
