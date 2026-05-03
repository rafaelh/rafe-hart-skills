from execute import execute_plan
from lib.journal import JobJournal
from undo import undo_job


class TestUndoJob:
    def test_reverses_a_moved_group(self, tmp_path):
        # Arrange: do a move so we have a real journal to undo.
        src = tmp_path / "src" / "img.jpg"
        src.parent.mkdir()
        src.write_bytes(b"original-content")
        dst = tmp_path / "dst" / "img.jpg"
        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(dst)}],
        }]
        journal = JobJournal(tmp_path / "state")
        execute_plan(plan, journal=journal)
        assert dst.exists() and not src.exists()

        # Act
        result = undo_job(journal=journal)

        # Assert
        assert src.read_bytes() == b"original-content"
        assert not dst.exists()
        assert result["restored"] == 1

    def test_dst_already_gone_is_skipped_not_failed(self, tmp_path):
        src = tmp_path / "src" / "img.jpg"
        src.parent.mkdir()
        src.write_bytes(b"hello")
        dst = tmp_path / "dst" / "img.jpg"
        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(dst)}],
        }]
        journal = JobJournal(tmp_path / "state")
        execute_plan(plan, journal=journal)

        # Simulate user deleting the dst manually before undo.
        dst.unlink()

        result = undo_job(journal=journal)
        assert result["skipped"] == 1
        assert result["restored"] == 0
        assert result["failed"] == 0

    def test_src_slot_occupied_is_skipped_not_clobbered(self, tmp_path):
        src = tmp_path / "src" / "img.jpg"
        src.parent.mkdir()
        src.write_bytes(b"original")
        dst = tmp_path / "dst" / "img.jpg"
        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(dst)}],
        }]
        journal = JobJournal(tmp_path / "state")
        execute_plan(plan, journal=journal)

        # User dropped a different file at the original src path.
        src.write_bytes(b"replacement-content")

        result = undo_job(journal=journal)
        assert result["skipped"] == 1
        assert src.read_bytes() == b"replacement-content"
        # dst still exists — undo refused to clobber.
        assert dst.exists()
