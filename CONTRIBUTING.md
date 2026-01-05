# Contributing to ScoreSource

Thanks for helping improve ScoreSource. This is a fixed-resolution (1280x400) LED scoreboard with multi-sport coverage. Please follow these guidelines to keep changes predictable and testable.

## Getting Started
- Use Python 3.10 or 3.11.
- Create a virtualenv: `python -m venv .venv && source .venv/bin/activate`.
- Install deps: `pip install -r requirements.txt`.
- Run the app: `python -m scoresource.main`.
- Run tests: `pytest`.

## Branches & Commits
- Branch naming: `feature/<topic>`, `fix/<topic>`, or `chore/<topic>`.
- Make small, focused commits with clear messages.
- Keep CHANGELOG.md up to date for user-facing changes.

## Testing
- Add or update tests for new logic; use mocks for API calls.
- Avoid network-dependent tests; prefer fixtures.
- Run `pytest` before opening a PR.

## Code Style
- Prefer typed function signatures where practical.
- Centralize shared logic in `scoresource/common/` when possible.
- Avoid silent failures; log with context using the shared logger.
- Keep LED layout constants centralized; avoid spreading magic numbers.

## Pull Requests
- Include a short summary, screenshots for UI changes, and test results.
- Mention known limitations or follow-ups.
- Link to relevant issues or TODO entries from `Change log_IMPROVEMENTS_NEEDED.md`.

## Issues
- When filing an issue, include reproduction steps, expected vs actual behavior, and logs if available.

## Security
- Report security concerns privately; do not open a public issue for sensitive findings.
