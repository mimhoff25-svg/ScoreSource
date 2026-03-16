"""Legacy launcher that delegates to ``scoresource.main``."""

from scoresource.main import main as run_main


def main() -> None:
    run_main()


if __name__ == "__main__":
    main()
