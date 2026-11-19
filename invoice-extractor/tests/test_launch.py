"""Tests for the one-click launcher (launch.py)."""

from pathlib import Path

import launch


def test_venv_python_path(tmp_path):
    path = launch.venv_python(tmp_path / ".venv")
    assert path.name in ("python", "python.exe")
    assert ".venv" in path.parts


def test_requirements_hash_changes_with_content(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text("streamlit\n")
    first = launch.requirements_hash(req)
    req.write_text("streamlit\npandas\n")
    assert launch.requirements_hash(req) != first and len(first) == 16


def test_app_not_running_on_closed_port():
    assert launch.app_running("http://localhost:9", timeout=0.2) is False


def test_required_packages_present_in_test_environment():
    assert launch.missing_in_this_python() == []


def test_double_click_files_exist_and_call_launcher():
    root = Path(launch.__file__).parent
    for name in ("Start Invoice Extractor.bat", "Start Invoice Extractor.command"):
        assert "launch.py" in (root / name).read_text()
