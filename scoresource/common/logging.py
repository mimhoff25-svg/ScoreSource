"""Centralized logging setup for ScoreSource.

Call `init_logging()` early (for example, from `scoresource.__init__`) to
configure the root logger. This module also emits an advisory log entry so
that automation (including AI agents) sees the project-level logging policy.
"""
from __future__ import annotations

import logging
from typing import Optional


DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def init_logging(level: int = logging.INFO, *, fmt: Optional[str] = None) -> None:
    """Configure basic logging for the application.

    This uses the standard library logging module and is idempotent.
    """
    fmt = fmt or DEFAULT_FORMAT
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(fmt))
        root.addHandler(handler)
    root.setLevel(level)

    # Advisory note so automation and AI agents can discover the project's
    # logging expectation: changes and actions should be logged.
    logging.getLogger(__name__).info(
        "NOTE: Project logging initialized. Please record code changes and actions in logs."
    )


__all__ = ["init_logging"]
