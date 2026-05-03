# /// script
# requires-python = ">=3.11"
# dependencies = ["platformdirs>=4"]
# ///
"""Bootstrap: verify Python, uv, and exiftool are available.

Usage:
    uv run bootstrap.py                  # Full check, writes state
    uv run bootstrap.py --check          # Fast: only verify recent state file is ready
"""

from __future__ import annotations

import argparse
import json
import os
import platform as _platform
import shutil
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from os import PathLike
from pathlib import Path
from typing import Any, TextIO

BOOTSTRAP_STATE_FILE = "bootstrap.json"
DEFAULT_MAX_AGE_DAYS = 30


def check_python_version(
    *,
    min_major: int,
    min_minor: int,
    version_info: tuple[int, int, int, str, int] | Any = None,
) -> dict[str, Any]:
    actual = version_info if version_info is not None else sys.version_info
    major, minor, micro = actual[0], actual[1], actual[2]
    version = f"{major}.{minor}.{micro}"
    if (major, minor) >= (min_major, min_minor):
        return {"name": "python", "status": "ok", "version": version}
    return {
        "name": "python",
        "status": "missing",
        "version": version,
        "install_hint": f"Python {min_major}.{min_minor}+ required; you have {version}.",
    }


def exiftool_install_hint(platform: str) -> str:
    if platform == "Windows":
        return (
            "Download the standalone Windows exe from https://exiftool.org. "
            "Rename `exiftool(-k).exe` to `exiftool.exe` and place it in this skill's `bin/` folder."
        )
    if platform == "Darwin":
        return "Run: brew install exiftool"
    return "Install exiftool from your package manager, e.g. `apt install libimage-exiftool-perl` on Debian/Ubuntu."


def resolve_exiftool(
    skill_root: str | PathLike[str] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> str | None:
    if skill_root is not None:
        bin_dir = Path(skill_root) / "bin"
        for name in ("exiftool", "exiftool.exe"):
            candidate = bin_dir / name
            if candidate.exists():
                return str(candidate)
    return which("exiftool")


def check_uv_available(*, which: Callable[[str], str | None] = shutil.which) -> dict[str, Any]:
    path = which("uv")
    if path:
        return {"name": "uv", "status": "ok", "path": path}
    return {
        "name": "uv",
        "status": "missing",
        "install_hint": "Install uv: https://docs.astral.sh/uv/getting-started/installation/",
    }


def run_all_checks(
    *,
    platform: str,
    version_info: tuple[int, int, int, str, int] | Any = None,
    which: Callable[[str], str | None] = shutil.which,
    skill_root: str | PathLike[str] | None = None,
    runner: Callable[[list[str]], Any] | None = None,
    min_python: tuple[int, int] = (3, 11),
    now: datetime | None = None,
) -> dict[str, Any]:
    py = check_python_version(min_major=min_python[0], min_minor=min_python[1], version_info=version_info)
    uv = check_uv_available(which=which)

    exiftool_path = resolve_exiftool(skill_root, which=which)
    if exiftool_path is None:
        exiftool_entry = {
            "name": "exiftool",
            "status": "missing",
            "install_hint": exiftool_install_hint(platform),
        }
        exiftool_version: str | None = None
    else:
        try:
            exiftool_version = verify_exiftool_works(exiftool_path, runner=runner)
            exiftool_entry = {
                "name": "exiftool",
                "status": "ok",
                "path": str(exiftool_path),
                "version": exiftool_version,
            }
        except RuntimeError as e:
            exiftool_version = None
            exiftool_entry = {
                "name": "exiftool",
                "status": "error",
                "path": str(exiftool_path),
                "error": str(e),
                "install_hint": exiftool_install_hint(platform),
            }

    results = [py, uv, exiftool_entry]
    ready = all(r["status"] == "ok" for r in results)
    current = now if now is not None else datetime.now(timezone.utc)
    return {
        "ready": ready,
        "checked_at": current.isoformat().replace("+00:00", "Z"),
        "exiftool_version": exiftool_version,
        "results": results,
    }


def verify_exiftool_works(
    exiftool_path: str | PathLike[str],
    *,
    runner: Callable[[list[str]], Any] | None = None,
) -> str:
    run = runner or _default_runner
    result = run([str(exiftool_path), "-ver"])
    if result.returncode != 0:
        stderr = getattr(result, "stderr", "") or ""
        raise RuntimeError(f"exiftool failed: {stderr.strip()}")
    return result.stdout.strip()


def _default_runner(cmd: list[str]) -> Any:
    import subprocess  # noqa: PLC0415

    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def write_bootstrap_state(state_dir: str | PathLike[str], state: dict[str, Any]) -> None:
    d = Path(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    target = d / BOOTSTRAP_STATE_FILE
    tmp = target.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def read_bootstrap_state(state_dir: str | PathLike[str]) -> dict[str, Any] | None:
    target = Path(state_dir) / BOOTSTRAP_STATE_FILE
    if not target.exists():
        return None
    with target.open(encoding="utf-8") as f:
        return json.load(f)


def main(
    argv: list[str],
    *,
    state_dir: str | PathLike[str],
    platform: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[[list[str]], Any] | None = None,
    skill_root: str | PathLike[str] | None = None,
    now: datetime | None = None,
    out: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="bootstrap")
    parser.add_argument("--check", action="store_true", help="Verify recent state file only; don't re-run checks")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=DEFAULT_MAX_AGE_DAYS,
        help=f"Treat state older than this as stale (default: {DEFAULT_MAX_AGE_DAYS})",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text")
    args = parser.parse_args(argv)
    output = out if out is not None else sys.stdout

    if args.check:
        fresh = is_bootstrap_fresh(state_dir, max_age_days=args.max_age_days, now=now)
        if args.json:
            print(json.dumps({"fresh": fresh}), file=output)
        elif not fresh:
            print("Bootstrap state missing or stale. Run `python bootstrap.py` to refresh.", file=output)
        return 0 if fresh else 1

    result = run_all_checks(
        platform=platform or _platform.system(),
        which=which,
        runner=runner,
        skill_root=skill_root,
        now=now,
    )
    write_bootstrap_state(state_dir, result)

    if args.json:
        print(json.dumps(result, indent=2), file=output)
        return 0 if result["ready"] else 1

    if result["ready"]:
        print("Bootstrap ready.", file=output)
        for r in result["results"]:
            ver = r.get("version", "")
            print(f"  - {r['name']}: ok {ver}".rstrip(), file=output)
        return 0

    print("Bootstrap incomplete. Address the following:", file=output)
    for r in result["results"]:
        if r["status"] == "ok":
            continue
        print(f"  - {r['name']}: {r['status']}", file=output)
        hint = r.get("install_hint")
        if hint:
            print(f"      {hint}", file=output)
    return 1


def is_bootstrap_fresh(
    state_dir: str | PathLike[str],
    *,
    max_age_days: int,
    now: datetime | None = None,
) -> bool:
    state = read_bootstrap_state(state_dir)
    if state is None:
        return False
    if not state.get("ready"):
        return False
    checked_at_str = state.get("checked_at")
    if not checked_at_str:
        return False
    try:
        checked_at = datetime.fromisoformat(checked_at_str.replace("Z", "+00:00"))
    except ValueError:
        return False
    if checked_at.tzinfo is None:
        checked_at = checked_at.replace(tzinfo=timezone.utc)
    current = now if now is not None else datetime.now(timezone.utc)
    age = current - checked_at
    return age.days < max_age_days


def default_state_dir() -> Path:
    """Resolve the per-OS state dir via platformdirs."""
    import platformdirs  # noqa: PLC0415  (lazy import; only needed at runtime)

    return Path(platformdirs.user_state_dir("photo-organise"))


def default_skill_root() -> Path:
    """The skill's root dir (one level above scripts/)."""
    return Path(__file__).resolve().parent.parent


if __name__ == "__main__":
    sys.exit(
        main(
            sys.argv[1:],
            state_dir=default_state_dir(),
            skill_root=default_skill_root(),
        )
    )
