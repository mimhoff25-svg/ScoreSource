"""ScoreSource multi-sport package."""

# Avoid importing the heavy Qt stack (PySide6) at package import time so
# consumers can import data-only submodules without GUI dependencies.
def main() -> None:
    from scoresource.main import main as _main

    return _main()


__all__ = ["main"]

# Initialize logging early so modules and automation see the project logging policy.
try:
    from .common.logging import init_logging

    init_logging()
except Exception:
    # Do not raise on import-time logging errors; best-effort only.
    pass
