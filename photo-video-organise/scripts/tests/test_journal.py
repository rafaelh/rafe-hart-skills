from lib.journal import JobJournal


class TestProgressLog:
    def test_appended_record_round_trips(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.append_progress({"group_id": "g_001", "status": "verified"})
        records = list(journal.iter_progress())
        assert records == [{"group_id": "g_001", "status": "verified"}]

    def test_multiple_appends_preserve_order(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.append_progress({"i": 1})
        journal.append_progress({"i": 2})
        journal.append_progress({"i": 3})
        assert [r["i"] for r in journal.iter_progress()] == [1, 2, 3]

    def test_iter_progress_on_empty_journal_yields_nothing(self, tmp_path):
        journal = JobJournal(tmp_path)
        assert list(journal.iter_progress()) == []


class TestStatus:
    def test_written_status_round_trips(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.write_status({"chunk": "IMG_2019/", "done": 312, "total": 482})
        assert journal.read_status() == {"chunk": "IMG_2019/", "done": 312, "total": 482}

    def test_status_overwrites_prior(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.write_status({"done": 1})
        journal.write_status({"done": 2})
        assert journal.read_status() == {"done": 2}

    def test_read_status_before_any_write_returns_none(self, tmp_path):
        assert JobJournal(tmp_path).read_status() is None

    def test_no_temp_file_left_after_write(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.write_status({"done": 1})
        leftover = list(tmp_path.glob("*.tmp"))
        assert leftover == []


class TestInProgressMarker:
    def test_fresh_journal_is_not_in_progress(self, tmp_path):
        assert JobJournal(tmp_path).is_in_progress is False

    def test_mark_then_check(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.mark_in_progress()
        assert journal.is_in_progress is True

    def test_mark_then_clear(self, tmp_path):
        journal = JobJournal(tmp_path)
        journal.mark_in_progress()
        journal.clear_in_progress()
        assert journal.is_in_progress is False

    def test_marker_visible_to_separate_journal_instance(self, tmp_path):
        JobJournal(tmp_path).mark_in_progress()
        assert JobJournal(tmp_path).is_in_progress is True
