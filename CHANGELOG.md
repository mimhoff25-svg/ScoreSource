# ScoreSource Changelog

This document records the historical evolution of the ScoreSource LED scoreboard software.
Dates are based on actual development conversations, UI iterations, and Codex-assisted changes.

Primary target: 1280x400 LED matrix displays  
Platform: Python, Raspberry Pi, low-latency rendering  
Initial league focus: NBA

---

## [0.0.1] – 2025-12-07
### Added
- ScoreSource project formally conceived.
- Core goal defined: a live sports scoreboard optimized specifically for LED panels.
- Initial discussion separating ScoreSource from generic scoreboard concepts.
- Early emphasis on *readability at distance* rather than desktop UI norms.

### Notes
- No fixed resolution enforced yet.
- All data assumed to be placeholder or simulated.

---

## [0.0.2] – 2025-12-09
### Added
- NBA selected as the first supported league.
- Early API ingestion concepts discussed.
- Team vs team visual layout proposed (home/away symmetry).
- Refresh-loop concepts introduced for near-real-time updates.

### Changed
- Project scope narrowed from “sports dashboard” to **dedicated scoreboard appliance**.

---

## [0.0.3] – 2025-12-12
### Added
- Team logos added to the visual design.
- Left/right team anchoring standardized.
- Initial team color usage introduced (flat fills).

### Issues
- Logo scaling inconsistent across teams.
- Text and logo competition for horizontal space.
- Early LED tests revealed legibility problems.

---

## [0.0.4] – 2025-12-15
### Added
- **Hard resolution lock: 1280x400**.
- Explicit rejection of responsive or resizable layouts.
- Pixel-space budgeting for scores, logos, and metadata.

### Changed
- Borders removed to reclaim LED real estate.
- Fonts resized and simplified for LED clarity.
- Layout tightened horizontally to reduce wasted pixels.

### Fixed
- Score clipping on double-digit values.
- Baseline misalignment between home and away scores.

---

## [0.0.5] – 2025-12-18
### Added
- Gradient backgrounds using team **primary + secondary colors**.
- Dynamic gradient blending per matchup.
- Background logic decoupled from layout logic.

### Changed
- Hard color blocks removed.
- Visual hierarchy clarified:
  - Score > Team Identity > Metadata

### Notes
- LED brightness and color wash considered in gradient tuning.

---

## [0.0.6] – 2025-12-22
### Added
- NBA boxscore support introduced.
- Player stat rows implemented.
- Early decisions on which stats matter for LED viewing.

### Changed
- Rendering code modularized:
  - Score layer
  - Background layer
  - Boxscore layer
- Performance considerations added for Raspberry Pi hardware.

### Issues
- Too much data visible at once.
- Stat density overwhelming on LED panels.

---

## [0.0.7] – 2025-12-27
### Added
- Scrollable player stat rows implemented.
- Mouse / touchpad drag interaction introduced.
- Extended stats (3PT, FG%, etc.) hidden behind horizontal scroll.

### Changed
- Shift from “show everything” to **progressive disclosure**.
- Stat rows treated as cards rather than static text.

### Fixed
- Input lag during drag gestures.
- Frame jitter during rapid stat refreshes.

---

## [0.0.8] – 2025-12-29
### Added
- Maximum of **5 visible players per team** enforced.
- Overflow players hidden behind scroll interaction.
- Visual indicators added to hint at hidden stats.

### Changed
- Boxscore spacing normalized.
- Reduced clutter for better at-a-glance readability.

### Notes
- Designed specifically for quick glances in live environments.

---

## [0.0.9] – 2026-01-02
### Added
- Logos re-centered with pixel-accurate alignment.
- Gradient contrast refined for LED brightness levels.
- Background transitions smoothed to avoid visual noise.

### Fixed
- Occasional gradient color inversion.
- Logo scaling inconsistencies between teams.

---

## [0.1.0] – 2026-01-04
### Added
- First stable LED-focused release.
- GitHub repository integration initiated.
- Project structure formalized.
- Changelog introduced to prevent historical drift.

### Changed
- Legacy experimental code removed.
- Cleanup pass for readability and maintainability.

### Notes
- Marks transition from prototype to maintainable system.

---

## [Unreleased]
### Added
- Cross-sport player cards now include condensed sport-aware profile fields, game stats, and career stats in a single compact layout.
- Team logos now render on the opposite side of the player headshot in the player-card hero row.
- Roster lineup entries preserve athlete ids so player-card lookups can target the correct profile.
- Added regression tests for player-profile disambiguation, lineup team-id recovery, and missing-headshot fallbacks.

### Changed
- Player-card headshots are larger and the surrounding layout is denser so the card stays inside the scoreboard bounds.
- The card no longer shows `Profile loaded from API`.
- Profile fetching now prefers full names plus jersey-aware matching to disambiguate duplicate names such as the Curry brothers.
- Team-id resolution now uses sport-aware tricode aliases when ESPN feeds return placeholder ids like `0`, `AWY`, or `HOM`.

### Fixed
- Prevented team logos from appearing in the player headshot slot when a real player photo is unavailable.
- Fixed NBA player-card mismatches caused by abbreviated lineup names and same-initial/same-last-name roster entries.
- Fixed several non-NBA card-photo failures by resolving roster team ids from tricodes before fetching profile data.

---

🤖 Codex Prompt (High-Discipline Version)

Use this when committing to GitHub or regenerating files:

You are working on the ScoreSource LED scoreboard project.

Task:
1. Create or update CHANGELOG.md in the repository root.
2. Use the provided changelog verbatim.
3. Do NOT invent, normalize, or reinterpret dates. you can merge if needed with current data
4. Preserve detailed notes, issues, and design rationale.
5. Ensure Markdown is GitHub-compatible.
6. If an existing changelog exists, merge chronologically without duplication.

Project Context:
- ScoreSource is a fixed-resolution (1280x400) LED scoreboard system.
- Designed for Raspberry Pi and low-latency rendering.
- NBA implemented first with boxscore scrolling UI.
- Development began December 2025.

Output:
- Confirm successful creation or update.
- Show repository tree if modified.
