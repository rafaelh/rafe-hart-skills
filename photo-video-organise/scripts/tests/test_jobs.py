from lib.journal import JobJournal
from jobs import list_jobs, purge_job


class TestListJobs:
    def test_returns_each_job_dir_with_status_summary(self, tmp_path):
        jobs_root = tmp_path / "jobs"
        a = JobJournal(jobs_root / "20260103T1000Z-import")
        a.write_status({"done": 100, "failed": 0, "total": 100})
        b = JobJournal(jobs_root / "20260104T1000Z-camera")
        b.mark_in_progress()
        b.write_status({"done": 5, "failed": 1, "total": 50})

        results = list_jobs(jobs_root)
        by_id = {j["job_id"]: j for j in results}
        assert "20260103T1000Z-import" in by_id
        assert "20260104T1000Z-camera" in by_id
        assert by_id["20260103T1000Z-import"]["in_progress"] is False
        assert by_id["20260104T1000Z-camera"]["in_progress"] is True
        assert by_id["20260103T1000Z-import"]["status"]["done"] == 100

    def test_missing_jobs_root_returns_empty(self, tmp_path):
        assert list_jobs(tmp_path / "does-not-exist") == []


class TestPurgeJob:
    def test_removes_job_state_dir(self, tmp_path):
        jobs_root = tmp_path / "jobs"
        journal = JobJournal(jobs_root / "test-job")
        journal.append_progress({"x": 1})
        assert (jobs_root / "test-job").exists()
        purge_job(jobs_root, "test-job")
        assert not (jobs_root / "test-job").exists()

    def test_purge_nonexistent_is_noop(self, tmp_path):
        # Should not raise.
        purge_job(tmp_path, "ghost-job")
