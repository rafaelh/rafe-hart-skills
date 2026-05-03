from lib.platform import (
    FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS,
    is_case_sensitive_fs,
    is_cloud_only,
    is_same_volume,
    normalize_for_compare,
)


class TestIsSameVolume:
    def test_two_files_in_same_dir_are_same_volume(self, tmp_path):
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("a")
        b.write_text("b")
        assert is_same_volume(a, b) is True


class TestIsCaseSensitiveFs:
    def test_matches_actual_fs_behavior(self, tmp_path):
        probe = tmp_path / "probe_for_case_check"
        probe.write_text("x")
        actual_case_sensitive = not (tmp_path / "PROBE_FOR_CASE_CHECK").exists()
        probe.unlink()
        assert is_case_sensitive_fs(tmp_path) is actual_case_sensitive


class TestNormalizeForCompare:
    def test_case_insensitive_collapses_case(self):
        a = normalize_for_compare("Photo.JPG", case_sensitive=False)
        b = normalize_for_compare("photo.jpg", case_sensitive=False)
        assert a == b

    def test_case_sensitive_preserves_case(self):
        a = normalize_for_compare("Photo.JPG", case_sensitive=True)
        b = normalize_for_compare("photo.jpg", case_sensitive=True)
        assert a != b


class TestIsCloudOnly:
    def test_non_windows_always_false(self, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_text("x")
        assert is_cloud_only(f, platform="Linux") is False
        assert is_cloud_only(f, platform="Darwin") is False

    def test_windows_with_recall_attr_is_cloud_only(self):
        attrs_with_recall = FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS | 0x20  # ARCHIVE bit also set
        result = is_cloud_only("X:/anything.jpg", platform="Windows", get_attrs=lambda _p: attrs_with_recall)
        assert result is True

    def test_windows_without_recall_attr_is_local(self):
        attrs_no_recall = 0x20  # plain ARCHIVE bit
        result = is_cloud_only("X:/anything.jpg", platform="Windows", get_attrs=lambda _p: attrs_no_recall)
        assert result is False
