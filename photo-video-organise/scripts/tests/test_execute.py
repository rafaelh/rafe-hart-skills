from lib.journal import JobJournal
from execute import execute_plan, move_with_retry


class TestExecutePlanSingleFile:
    def test_clear_path_moves_file_and_records_in_journal(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        src = src_dir / "img.jpg"
        src.write_bytes(b"hello")

        dst_dir = tmp_path / "dst"
        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(dst_dir / "img.jpg")}],
        }]
        journal = JobJournal(tmp_path / "state")

        result = execute_plan(plan, journal=journal)

        assert (dst_dir / "img.jpg").read_bytes() == b"hello"
        assert not src.exists()
        assert result["done"] == 1
        assert result["failed"] == 0
        records = list(journal.iter_progress())
        assert any(r["status"] == "moved" for r in records)


class TestGroupAtomicity:
    def test_failed_second_move_rolls_back_first(self, tmp_path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        a = src_dir / "a.jpg"
        b = src_dir / "b.jpg"
        a.write_bytes(b"A")
        b.write_bytes(b"B")

        dst_dir = tmp_path / "dst"
        dst_dir.mkdir()
        # blocker is a file — mkdir(blocker/sub) will fail with NotADirectoryError.
        blocker = dst_dir / "blocker"
        blocker.write_bytes(b"X")

        plan = [{
            "primary_file": str(a),
            "action": "move",
            "destination_files": [
                {"src": str(a), "dst": str(dst_dir / "a.jpg")},
                {"src": str(b), "dst": str(blocker / "sub" / "b.jpg")},  # parent is a file
            ],
        }]
        journal = JobJournal(tmp_path / "state")

        result = execute_plan(plan, journal=journal)
        assert result["failed"] == 1
        assert result["done"] == 0
        # Both source files are preserved.
        assert a.read_bytes() == b"A"
        assert b.read_bytes() == b"B"
        # Nothing leaked to destination.
        assert not (dst_dir / "a.jpg").exists()


class TestSkipActions:
    def test_skip_already_organized_does_not_move_and_records_skip(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"hello")
        dst = tmp_path / "dst.jpg"
        plan = [{
            "primary_file": str(src),
            "action": "skip:already-organized",
            "destination_files": [{"src": str(src), "dst": str(dst)}],
        }]
        journal = JobJournal(tmp_path / "state")
        result = execute_plan(plan, journal=journal)
        assert result["done"] == 0
        assert result["failed"] == 0
        assert result["skipped"] == 1
        assert src.exists()
        assert not dst.exists()
        assert any(r["status"] == "skipped" for r in journal.iter_progress())


class TestInProgressMarker:
    def test_marker_cleared_after_normal_run(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"x")
        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(tmp_path / "dst" / "src.jpg")}],
        }]
        journal = JobJournal(tmp_path / "state")
        execute_plan(plan, journal=journal)
        assert journal.is_in_progress is False

    def test_marker_cleared_even_when_groups_fail(self, tmp_path):
        src = tmp_path / "src.jpg"
        src.write_bytes(b"x")
        # blocker is a file — destination parent path can't be made.
        blocker = tmp_path / "blocker"
        blocker.write_bytes(b"X")
        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(blocker / "sub" / "src.jpg")}],
        }]
        journal = JobJournal(tmp_path / "state")
        execute_plan(plan, journal=journal)
        assert journal.is_in_progress is False


class TestCollisionRouting:
    def _setup_paths(self, tmp_path):
        source_root = tmp_path / "source"
        dest_root = tmp_path / "dest"
        to_delete = dest_root / "To_Delete" / "duplicates"
        conflicts = dest_root / "_conflicts"
        return source_root, dest_root, to_delete, conflicts

    def test_dst_with_identical_content_routes_group_to_to_delete(self, tmp_path):
        source_root, dest_root, to_delete, conflicts = self._setup_paths(tmp_path)
        src_dir = source_root / "import"
        src_dir.mkdir(parents=True)
        src = src_dir / "img.jpg"
        src.write_bytes(b"identical-content")

        # Pre-existing identical file at the planned destination.
        dest_dir = dest_root / "2019" / "2019-08"
        dest_dir.mkdir(parents=True)
        existing = dest_dir / "img.jpg"
        existing.write_bytes(b"identical-content")

        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(existing)}],
        }]
        journal = JobJournal(tmp_path / "state")
        result = execute_plan(
            plan,
            journal=journal,
            source_root=source_root,
            to_delete_root=to_delete,
            conflicts_root=conflicts,
        )
        # Source moved into To_Delete/duplicates/, preserving folder structure.
        assert not src.exists()
        relocated = to_delete / "import" / "img.jpg"
        assert relocated.read_bytes() == b"identical-content"
        # Pre-existing destination untouched.
        assert existing.read_bytes() == b"identical-content"
        # Stats: group counted as quarantined-duplicate.
        assert result["duplicates"] == 1

    def test_dst_with_different_content_routes_group_to_conflicts(self, tmp_path):
        source_root, dest_root, to_delete, conflicts = self._setup_paths(tmp_path)
        src_dir = source_root / "import"
        src_dir.mkdir(parents=True)
        src = src_dir / "img.jpg"
        src.write_bytes(b"source-version")

        dest_dir = dest_root / "2019" / "2019-08"
        dest_dir.mkdir(parents=True)
        existing = dest_dir / "img.jpg"
        existing.write_bytes(b"completely-different-content")

        plan = [{
            "primary_file": str(src),
            "action": "move",
            "destination_files": [{"src": str(src), "dst": str(existing)}],
        }]
        journal = JobJournal(tmp_path / "state")
        result = execute_plan(
            plan,
            journal=journal,
            source_root=source_root,
            to_delete_root=to_delete,
            conflicts_root=conflicts,
        )
        # Source moved into _conflicts/, preserving folder structure.
        assert not src.exists()
        relocated = conflicts / "import" / "img.jpg"
        assert relocated.read_bytes() == b"source-version"
        # Pre-existing destination untouched.
        assert existing.read_bytes() == b"completely-different-content"
        assert result["conflicts"] == 1


class TestMoveWithRetry:
    def test_succeeds_on_first_attempt_when_no_error(self):
        calls = []
        sleeps = []

        def mover(s, d):
            calls.append((s, d))

        move_with_retry(mover, "a", "b", attempts=3, backoff=0.5, sleep_fn=sleeps.append)
        assert calls == [("a", "b")]
        assert sleeps == []

    def test_retries_after_permission_error_then_succeeds(self):
        attempts = [0]
        sleeps = []

        def flaky(s, d):
            attempts[0] += 1
            if attempts[0] == 1:
                raise PermissionError("locked")
            return None

        move_with_retry(flaky, "a", "b", attempts=3, backoff=0.5, sleep_fn=sleeps.append)
        assert attempts[0] == 2
        assert sleeps == [0.5]

    def test_uses_exponential_backoff_across_retries(self):
        sleeps = []

        def always_fail(s, d):
            raise PermissionError("locked")

        try:
            move_with_retry(always_fail, "a", "b", attempts=4, backoff=0.5, sleep_fn=sleeps.append)
        except PermissionError:
            pass
        # 3 sleeps between 4 attempts: 0.5, 1.0, 2.0
        assert sleeps == [0.5, 1.0, 2.0]

    def test_non_retryable_error_raises_immediately(self):
        calls = [0]
        sleeps = []

        def bad(s, d):
            calls[0] += 1
            raise ValueError("not retryable")

        try:
            move_with_retry(bad, "a", "b", attempts=3, backoff=0.5, sleep_fn=sleeps.append)
        except ValueError:
            pass
        assert calls[0] == 1
        assert sleeps == []


class TestStatusSnapshot:
    def test_final_status_written_with_counts(self, tmp_path):
        a = tmp_path / "a.jpg"
        b = tmp_path / "b.jpg"
        a.write_bytes(b"x")
        b.write_bytes(b"y")
        plan = [
            {
                "primary_file": str(a),
                "action": "move",
                "destination_files": [{"src": str(a), "dst": str(tmp_path / "out" / "a.jpg")}],
            },
            {
                "primary_file": str(b),
                "action": "skip:already-organized",
                "destination_files": [{"src": str(b), "dst": str(b)}],
            },
        ]
        journal = JobJournal(tmp_path / "state")
        execute_plan(plan, journal=journal)
        status = journal.read_status()
        assert status is not None
        assert status["done"] == 1
        assert status["skipped"] == 1
        assert status["total"] == 2
