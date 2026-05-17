import pytest

import scoresource.main as main_module
import pyside.logic as legacy_logic
import pyside.realtime as legacy_realtime
import pyside.ui as legacy_ui
from scoresource.logic import ScoreSourceLogic as ActiveLogic
from scoresource.realtime import RealTimeGameState as ActiveRealTimeGameState
from scoresource.ui import ScoreSourceWindow
from scoresource.logic import ScoreSourceLogic
from scoresource.registry import (
    canonicalize_sport_name,
    display_name_for_sport,
    get_sport_config,
)


def test_registry_canonicalizes_display_names():
    assert canonicalize_sport_name("NCAA Basketball") == "NCAA BASKETBALL"
    assert canonicalize_sport_name("NCAA Football") == "NCAA FOOTBALL"
    assert display_name_for_sport("NCAA BASKETBALL") == "NCAA Basketball"
    assert display_name_for_sport("NCAA FOOTBALL") == "NCAA Football"

    config = get_sport_config("NCAA BASKETBALL")
    assert config is not None
    assert config["display_name"] == "NCAA Basketball"
    assert config["sport_key"] == "NCAA BASKETBALL"


class _SwitchWindow:
    def __init__(self) -> None:
        self.backend = None
        self.sport_name = "NBA"
        self._sport_key = "NBA"
        self.logic = ScoreSourceLogic(default_sport="NBA")
        self._sport_options = []
        self._sport_logo_path = None
        self.table_headers = None
        self.updated_logo_path = None
        self.window_title = None
        self.refresh_count = 0

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def update_table_headers(self, headers) -> None:
        self.table_headers = headers

    def update_league_logo(self, logo_path) -> None:
        self.updated_logo_path = logo_path

    def refresh_scores(self) -> None:
        self.refresh_count += 1


def test_switch_sport_uses_registry_internal_key():
    window = _SwitchWindow()

    main_module._switch_sport("NCAA Basketball", window)

    assert window.sport_name == "NCAA Basketball"
    assert window._sport_key == "NCAA BASKETBALL"
    assert window.logic.current_sport == "NCAA BASKETBALL"
    assert window.window_title == "ScoreSource – NCAA Basketball"
    assert window.refresh_count == 1


def test_main_smoke(monkeypatch):
    events = {"shown": False, "exec_called": False}

    class DummyApp:
        def __init__(self, argv):
            events["argv"] = list(argv)

        def exec(self) -> int:
            events["exec_called"] = True
            return 0

    class DummyWindow:
        def __init__(self, **kwargs):
            events["window_kwargs"] = kwargs
            self._sport_key = None

        def show(self) -> None:
            events["shown"] = True

    monkeypatch.setattr(main_module, "QApplication", DummyApp)
    monkeypatch.setattr(main_module, "ScoreSourceWindow", DummyWindow)
    monkeypatch.setattr(main_module, "_acquire_instance_lock", lambda: True)
    monkeypatch.setattr(main_module.sys, "exit", lambda code=0: (_ for _ in ()).throw(SystemExit(code)))

    with pytest.raises(SystemExit) as excinfo:
        main_module.main()

    assert excinfo.value.code == 0
    assert events["shown"] is True
    assert events["exec_called"] is True
    assert events["window_kwargs"]["sport_name"] == "NBA"
    assert events["window_kwargs"]["logic"].current_sport == "NBA"


def test_main_exits_when_instance_lock_is_held(monkeypatch, capsys):
    events = {"app_created": False, "window_created": False}

    class DummyApp:
        def __init__(self, argv):
            events["app_created"] = True

    class DummyWindow:
        def __init__(self, **kwargs):
            events["window_created"] = True

    monkeypatch.setattr(main_module, "_acquire_instance_lock", lambda: False)
    monkeypatch.setattr(main_module, "QApplication", DummyApp)
    monkeypatch.setattr(main_module, "ScoreSourceWindow", DummyWindow)

    main_module.main()

    captured = capsys.readouterr()
    assert "already running" in captured.err
    assert events["app_created"] is False
    assert events["window_created"] is False


def test_sports_package_imports_cleanly():
    import scoresource.sports as sports_pkg
    from scoresource.sports import nba as sports_nba

    assert "nba" in sports_pkg.__all__
    assert callable(sports_nba.fetch_scores)


def test_legacy_pyside_shims_point_to_active_modules():
    assert issubclass(legacy_logic.ScoreSourceLogic, ActiveLogic)
    assert legacy_realtime.RealTimeGameState is ActiveRealTimeGameState
    assert legacy_ui.ScoreSourceWindow is ScoreSourceWindow
