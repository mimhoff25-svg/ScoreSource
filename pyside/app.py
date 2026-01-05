"""Launcher for ScoreSource multi-sport (delegates to scoresource.main)."""

import sys
from PySide6.QtWidgets import QApplication

from scoresource.main import main as run_main


def main():
    run_main()


if __name__ == "__main__":
    main()
