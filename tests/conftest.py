from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def temp_home(monkeypatch, tmp_path):
    """Redirect ~/.moodlist to a temp directory for the duration of a test."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    moodlist_dir = fake_home / ".moodlist"
    moodlist_dir.mkdir()
    yield moodlist_dir


@pytest.fixture
def sample_flac(tmp_path):
    """Return path to a 1-second silent FLAC for tag-roundtrip tests."""
    src = Path(__file__).parent / "fixtures" / "silence.flac"
    if not src.exists():
        pytest.skip("fixture silence.flac not present; see Task 2 step 1")
    dst = tmp_path / "silence.flac"
    dst.write_bytes(src.read_bytes())
    return dst
