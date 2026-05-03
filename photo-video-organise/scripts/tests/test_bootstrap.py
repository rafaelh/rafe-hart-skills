from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import io

from bootstrap import (
    check_python_version,
    exiftool_install_hint,
    is_bootstrap_fresh,
    main,
    read_bootstrap_state,
    resolve_exiftool,
    run_all_checks,
    verify_exiftool_works,
    write_bootstrap_state,
)


class TestCheckPythonVersion:
    def test_current_python_is_ok(self):
        # Tests run on Python 3.11+ per project requirement
        result = check_python_version(min_major=3, min_minor=11)
        assert result["status"] == "ok"
        assert result["name"] == "python"

    def test_too_old_python_is_missing(self):
        old = (3, 10, 0, "final", 0)
        result = check_python_version(min_major=3, min_minor=11, version_info=old)
        assert result["status"] == "missing"
        assert "3.11" in result["install_hint"]


class TestResolveExiftool:
    def test_returns_none_when_neither_bundled_nor_on_path(self, tmp_path):
        skill_root = tmp_path
        (skill_root / "bin").mkdir()
        result = resolve_exiftool(skill_root, which=lambda _: None)
        assert result is None

    def test_prefers_bundled_over_path(self, tmp_path):
        skill_root = tmp_path
        bin_dir = skill_root / "bin"
        bin_dir.mkdir()
        bundled = bin_dir / "exiftool"
        bundled.write_text("#!/bin/sh\necho fake\n")
        bundled.chmod(0o755)
        result = resolve_exiftool(skill_root, which=lambda _: "/usr/bin/exiftool")
        assert result == str(bundled)

    def test_falls_back_to_path_when_no_bundled(self, tmp_path):
        skill_root = tmp_path
        (skill_root / "bin").mkdir()
        result = resolve_exiftool(skill_root, which=lambda _: "/usr/bin/exiftool")
        assert result == "/usr/bin/exiftool"


class TestExiftoolInstallHint:
    def test_windows_mentions_exe_download(self):
        hint = exiftool_install_hint("Windows")
        assert "exiftool.org" in hint
        assert ".exe" in hint
        assert "bin" in hint

    def test_macos_mentions_brew(self):
        hint = exiftool_install_hint("Darwin")
        assert "brew install exiftool" in hint

    def test_linux_mentions_apt_or_package(self):
        hint = exiftool_install_hint("Linux")
        assert "exiftool" in hint.lower()


class TestBootstrapState:
    def test_write_then_read_round_trips(self, tmp_path):
        state = {"ready": True, "exiftool_version": "12.50", "checked_at": "2026-05-03T10:00:00Z"}
        write_bootstrap_state(tmp_path, state)
        assert read_bootstrap_state(tmp_path) == state

    def test_read_when_no_state_returns_none(self, tmp_path):
        assert read_bootstrap_state(tmp_path) is None


class TestIsBootstrapFresh:
    def test_no_state_is_not_fresh(self, tmp_path):
        assert is_bootstrap_fresh(tmp_path, max_age_days=30) is False

    def test_recent_ready_state_is_fresh(self, tmp_path):
        now = datetime(2026, 5, 3, tzinfo=timezone.utc)
        recent = (now - timedelta(days=5)).isoformat()
        write_bootstrap_state(tmp_path, {"ready": True, "checked_at": recent})
        assert is_bootstrap_fresh(tmp_path, max_age_days=30, now=now) is True

    def test_old_state_is_not_fresh(self, tmp_path):
        now = datetime(2026, 5, 3, tzinfo=timezone.utc)
        old = (now - timedelta(days=45)).isoformat()
        write_bootstrap_state(tmp_path, {"ready": True, "checked_at": old})
        assert is_bootstrap_fresh(tmp_path, max_age_days=30, now=now) is False

    def test_state_with_ready_false_is_not_fresh(self, tmp_path):
        now = datetime(2026, 5, 3, tzinfo=timezone.utc)
        recent = (now - timedelta(days=1)).isoformat()
        write_bootstrap_state(tmp_path, {"ready": False, "checked_at": recent})
        assert is_bootstrap_fresh(tmp_path, max_age_days=30, now=now) is False


class TestVerifyExiftoolWorks:
    def test_returns_version_when_runner_reports_success(self):
        def fake_runner(cmd):
            return SimpleNamespace(returncode=0, stdout="12.50\n", stderr="")
        version = verify_exiftool_works("/fake/exiftool", runner=fake_runner)
        assert version == "12.50"

    def test_raises_when_runner_reports_failure(self):
        def fake_runner(cmd):
            return SimpleNamespace(returncode=1, stdout="", stderr="not found")
        try:
            verify_exiftool_works("/fake/exiftool", runner=fake_runner)
        except RuntimeError as e:
            assert "not found" in str(e) or "exiftool" in str(e).lower()
        else:
            raise AssertionError("expected RuntimeError")


class TestRunAllChecks:
    def _ok_runner(self, cmd):
        return SimpleNamespace(returncode=0, stdout="12.50\n", stderr="")

    def test_ready_when_all_dependencies_present(self):
        result = run_all_checks(
            platform="Darwin",
            version_info=(3, 14, 0, "final", 0),
            which=lambda cmd: f"/usr/bin/{cmd}",
            skill_root=None,
            runner=self._ok_runner,
        )
        assert result["ready"] is True
        assert result["exiftool_version"] == "12.50"
        assert result["checked_at"]  # timestamp present

    def test_not_ready_when_exiftool_missing(self):
        def which_only_uv(cmd):
            return "/usr/bin/uv" if cmd == "uv" else None
        result = run_all_checks(
            platform="Darwin",
            version_info=(3, 14, 0, "final", 0),
            which=which_only_uv,
            skill_root=None,
            runner=self._ok_runner,
        )
        assert result["ready"] is False
        # The exiftool entry should describe the failure with a hint
        exiftool_entry = next(r for r in result["results"] if r["name"] == "exiftool")
        assert exiftool_entry["status"] == "missing"
        assert "brew install exiftool" in exiftool_entry["install_hint"]

    def test_not_ready_when_python_too_old(self):
        result = run_all_checks(
            platform="Darwin",
            version_info=(3, 10, 0, "final", 0),
            which=lambda cmd: f"/usr/bin/{cmd}",
            skill_root=None,
            runner=self._ok_runner,
        )
        assert result["ready"] is False
        py_entry = next(r for r in result["results"] if r["name"] == "python")
        assert py_entry["status"] == "missing"


class TestMainCli:
    def _ok_runner(self, cmd):
        return SimpleNamespace(returncode=0, stdout="12.50\n", stderr="")

    def _ok_kwargs(self, state_dir):
        return {
            "state_dir": state_dir,
            "platform": "Darwin",
            "which": lambda cmd: f"/usr/bin/{cmd}",
            "runner": self._ok_runner,
        }

    def test_check_mode_with_no_state_returns_nonzero(self, tmp_path):
        out = io.StringIO()
        rc = main(["--check"], state_dir=tmp_path, out=out)
        assert rc != 0

    def test_full_run_writes_state_and_returns_zero_when_ready(self, tmp_path):
        out = io.StringIO()
        rc = main([], out=out, **self._ok_kwargs(tmp_path))
        assert rc == 0
        state = read_bootstrap_state(tmp_path)
        assert state is not None
        assert state["ready"] is True

    def test_check_mode_after_full_run_returns_zero(self, tmp_path):
        out = io.StringIO()
        main([], out=out, **self._ok_kwargs(tmp_path))
        rc = main(["--check"], state_dir=tmp_path, out=out)
        assert rc == 0

    def test_full_run_returns_nonzero_when_dependency_missing(self, tmp_path):
        out = io.StringIO()
        which_no_exiftool = lambda cmd: "/usr/bin/uv" if cmd == "uv" else None  # noqa: E731
        rc = main(
            [],
            state_dir=tmp_path,
            platform="Darwin",
            which=which_no_exiftool,
            runner=self._ok_runner,
            out=out,
        )
        assert rc != 0
        # Output should mention how to install exiftool
        assert "exiftool" in out.getvalue().lower()
