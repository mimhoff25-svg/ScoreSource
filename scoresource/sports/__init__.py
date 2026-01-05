"""Sports registry exports.

We avoid importing Qt-backed UI classes at package import time so the data
fetchers (scoresource.sports.nba, etc.) can be used without PySide6 present.
"""

__all__ = ["SportConfig", "get_config", "get_sport_names", "load_backend", "icon_map"]


def __getattr__(name):
    if name in __all__:
        from . import registry as _registry

        return getattr(_registry, name)
    raise AttributeError(name)
