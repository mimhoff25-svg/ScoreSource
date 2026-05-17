from pathlib import Path

from scoresource.common import paths


def test_windows_cache_dir_uses_localappdata(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\Test\AppData\Local")
    monkeypatch.delenv("SCORESOURCE_CACHE_DIR", raising=False)

    assert paths.cache_dir() == Path(r"C:\Users\Test\AppData\Local") / "ScoreSource" / "Cache"


def test_linux_state_dir_uses_xdg_state_home(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/xdg-state")
    monkeypatch.delenv("SCORESOURCE_STATE_DIR", raising=False)

    assert paths.state_dir() == Path("/tmp/xdg-state") / "scoresource"


def test_log_dir_respects_override(monkeypatch):
    monkeypatch.setenv("SCORESOURCE_LOG_DIR", "/tmp/scoresource-logs")

    assert paths.log_dir() == Path("/tmp/scoresource-logs")
