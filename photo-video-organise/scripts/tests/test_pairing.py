from lib.pairing import (
    EXT_CLASSES,
    PRIMARY_PRIORITY,
    group_pairs,
    select_primary,
)


def entry(path):
    from pathlib import Path

    return {"path": path, "ext": Path(path).suffix.lower()}


DEFAULT_PAIR_EXTS = frozenset({".cr2", ".cr3", ".jpg", ".jpeg", ".heic", ".mov", ".mp4", ".tif", ".xmp"})


class TestGroupPairs:
    def test_files_with_same_stem_in_same_folder_pair(self):
        entries = [
            entry("/photos/IMG_1234.CR2"),
            entry("/photos/IMG_1234.JPG"),
        ]
        groups = group_pairs(entries, pair_extensions=DEFAULT_PAIR_EXTS)
        assert len(groups) == 1
        assert len(groups[0]["members"]) == 2
        assert groups[0]["stem"] == "IMG_1234"

    def test_cross_folder_same_stem_does_not_pair(self):
        entries = [
            entry("/photos/2019/IMG_1234.JPG"),
            entry("/photos/2020/IMG_1234.JPG"),
        ]
        groups = group_pairs(entries, pair_extensions=DEFAULT_PAIR_EXTS)
        assert len(groups) == 2

    def test_extension_outside_allowlist_does_not_pair(self):
        # IMG_1234.txt should not pair with IMG_1234.jpg even though stems match.
        entries = [
            entry("/photos/IMG_1234.JPG"),
            entry("/photos/IMG_1234.txt"),
        ]
        groups = group_pairs(entries, pair_extensions=DEFAULT_PAIR_EXTS)
        assert len(groups) == 2

    def test_case_insensitive_stem_matching_when_fs_is_case_insensitive(self):
        # IMG_1234.cr2 and img_1234.jpg should pair on a case-insensitive FS.
        entries = [
            entry("/photos/IMG_1234.CR2"),
            entry("/photos/img_1234.jpg"),
        ]
        groups = group_pairs(entries, pair_extensions=DEFAULT_PAIR_EXTS, case_sensitive=False)
        assert len(groups) == 1
        assert len(groups[0]["members"]) == 2

    def test_singleton_files_become_groups_of_one(self):
        entries = [entry("/photos/IMG_1234.JPG")]
        groups = group_pairs(entries, pair_extensions=DEFAULT_PAIR_EXTS)
        assert len(groups) == 1
        assert len(groups[0]["members"]) == 1


class TestSelectPrimary:
    def test_raw_wins_over_jpeg(self):
        members = [entry("/p/IMG.JPG"), entry("/p/IMG.CR2")]
        primary = select_primary(members, priority=PRIMARY_PRIORITY, ext_classes=EXT_CLASSES)
        assert primary["path"] == "/p/IMG.CR2"

    def test_heic_wins_over_jpeg_and_video(self):
        members = [entry("/p/IMG.MOV"), entry("/p/IMG.HEIC"), entry("/p/IMG.JPG")]
        primary = select_primary(members, priority=PRIMARY_PRIORITY, ext_classes=EXT_CLASSES)
        assert primary["path"] == "/p/IMG.HEIC"

    def test_xmp_sidecar_loses_to_anything(self):
        members = [entry("/p/IMG.xmp"), entry("/p/IMG.JPG")]
        primary = select_primary(members, priority=PRIMARY_PRIORITY, ext_classes=EXT_CLASSES)
        assert primary["path"] == "/p/IMG.JPG"

    def test_singleton_returns_itself(self):
        [single] = [entry("/p/IMG.CR2")]
        primary = select_primary([single], priority=PRIMARY_PRIORITY, ext_classes=EXT_CLASSES)
        assert primary["path"] == "/p/IMG.CR2"


class TestGroupPairsPrimary:
    def test_group_primary_is_highest_priority_member(self):
        entries = [
            entry("/photos/IMG_1234.JPG"),
            entry("/photos/IMG_1234.CR2"),
            entry("/photos/IMG_1234.xmp"),
        ]
        [group] = group_pairs(entries, pair_extensions=DEFAULT_PAIR_EXTS)
        assert group["primary"]["path"] == "/photos/IMG_1234.CR2"
