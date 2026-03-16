# NOTE: All changes and actions MUST be logged.
# AI agents and automation should record what they change and why in project logs.
# This ensures traceability and helps debugging; follow existing logging conventions.

# ScoreSource - Areas Needing Improvement

## Change Log
- 2025-01-03: Fixed missing `os` import in `scoresource/nfl.py` after time formatter refactor; test suite now passes (`PYTHONPATH=. .venv/bin/pytest`).
- 2025-01-03: Unified start time formatting across sports: same-day shows time only, within 7 days shows weekday + time, beyond 7 days shows M/D + time; final games display "Final". Implemented in `scoresource/logic.py` normalization.
- 2025-01-03: Deduplicated per-sport start time helpers into `scoresource/common/timefmt.py`; NFL/NHL/MLB/NBA backends now use the shared formatter.
- 2025-01-03: Hardened `scoresource/common/timefmt.py` parsing (handles ms epochs, offset-less ISO strings, and naive values) to improve schedule headers across sports.
- 2025-01-03: Updated PySide NBA frontend to use shared start-time formatter (fixes schedule lines showing fixed weekday like "Sat").
- 2025-01-03: MLS backend now uses shared start-time formatter for schedule headers (future dates show weekday/date consistently).
- 2025-01-03: Removed unused `websockets` dependency from `requirements.txt` and deleted cache dirs (`__pycache__`, `.pytest_cache`).
- 2025-01-03: Added `SCORESOURCE_REALTIME_ENABLED` gate in `scoresource/logic.py` to allow disabling realtime.
- 2025-01-03: Moved `alphy` to `/home/mike/projects/alphy` and updated launcher/desktop paths.
- 2025-01-03: Updated real-time section to reflect polling-based implementation and remaining gaps.
- 2026-01-03: Added centralized logging initializer (`scoresource/common/logging.py`) and configured package import to initialize logging with an advisory note for automation.
- 2026-01-03: Instrumented modules to surface failures via logs: `scoresource/common/utils.py` (`http_get_json`), `scoresource/logic.py` (backend fetch fallbacks), `scoresource/nhl.py`, `scoresource/sports/nhl.py`, and `scoresource/sports/nhl_backend.py`.
- 2026-01-03: Hardened tests by updating `tests/test_backends.py` to skip when upstream returns no games (avoids IndexError in CI).
- 2026-01-03: Prepended logging advisory notes to top-level improvement docs (`alphy/IMPROVEMENTS_TODO.md` and `ScoreScource/IMPROVEMENTS_NEEDED.md`) to instruct AI/automation to always log actions.

## Executive Summary
After reviewing the ScoreSource codebase, I've identified several areas where improvements are needed across code quality, architecture, error handling, performance, and feature completeness.

---

## 1. CRITICAL ISSUES

### 1.1 Real-time Implementation (MEDIUM PRIORITY)
**Location:** `scoresource/realtime.py`, `pyside/realtime.py`, `scoresource/logic.py`

**Status:** WebSocket placeholder removed; real-time is now polling-based against NBA live data endpoints.

**Remaining Issues:**
- Polling is NBA-only; other sports return a null client by design
- Errors are swallowed; no logging or metrics for failures
- No retry/backoff strategy on repeated errors
- Env-based toggle exists but needs documentation (`SCORESOURCE_REALTIME_ENABLED`)
- `websockets` is still listed in requirements but appears unused

**Recommendations:**
- Add rate-limited logging around fetch failures
- Implement backoff/jitter for repeated errors
- Document realtime env vars:
  - `SCORESOURCE_REALTIME_ENABLED`
  - `SCORESOURCE_REALTIME_POLL_INTERVAL`
  - `SCORESOURCE_REALTIME_TIMEOUT`
- Remove `websockets` from `requirements.txt` if not needed

### 1.2 NFL Module - Excessive Complexity
**Location:** `scoresource/nfl.py` (1000+ lines)

**Issues:**
- Single file contains 1000+ lines of code
- Multiple responsibilities: API fetching, data parsing, caching, logo management
- Hard to maintain and test
- Violates Single Responsibility Principle

**Recommendations:**
- Split into modules:
  - `nfl/api.py` - API calls and data fetching
  - `nfl/parser.py` - Data parsing and normalization
  - `nfl/cache.py` - Caching logic
  - `nfl/models.py` - Data models
  - `nfl/constants.py` - Team colors, headers, etc.

### 1.3 Error Handling - Silent Failures
**Location:** Throughout codebase

**Issues:**
```python
# Example from nfl.py:
try:
    resp = _session.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
except Exception:
    return {}  # Silent failure - no logging
```

**Impact:** Debugging is difficult when API calls fail

**Recommendations:**
- Add proper logging framework
- Log errors with context
- Provide user-friendly error messages
- Implement retry logic for transient failures

---

## 2. CODE QUALITY ISSUES

### 2.1 Inconsistent Error Handling Patterns

**Examples:**
```python
# Pattern 1: Return None
def _fetch_data():
    try:
        return data
    except Exception:
        return None

# Pattern 2: Return empty dict
def _fetch_data():
    try:
        return data
    except Exception:
        return {}

# Pattern 3: Return empty list
def _fetch_data():
    try:
        return data
    except Exception:
        return []
```

**Recommendation:** Standardize on one pattern or use Result types

### 2.2 Magic Numbers and Hardcoded Values

**Location:** `scoresource/nfl.py`, `scoresource/ui/window.py`

**Issues:**
```python
# From nfl.py:
BOXSCORE_TTL_FINAL = 60 * 60 * 24 * 7  # What does this represent?
LIVE_START_GRACE_SEC = 10 * 60  # Why 10 minutes?
LIVE_START_MAX_SEC = 6 * 60 * 60  # Why 6 hours?

# From ui.py:
WINDOW_WIDTH = 1280  # Should be configurable
WINDOW_HEIGHT = 400
TICKER_SPEED_PX = 16.0
```

**Recommendations:**
- Extract to named constants with documentation
- Make UI dimensions configurable
- Add comments explaining the reasoning

### 2.3 Duplicate Code Across Sport Modules

**Issue:** Similar patterns repeated in nba.py, nfl.py, nhl.py, etc.

**Examples:**
- Logo fetching and caching logic
- API request patterns
- Data normalization
- Error handling

**Recommendation:** Create base classes or shared utilities:
```python
# Proposed structure:
class BaseSportAPI:
    def fetch_scoreboard(self):
        pass
    
    def fetch_boxscore(self, game_id):
        pass
    
    def get_team_logo(self, team_id, tricode):
        pass

class NFLApi(BaseSportAPI):
    # NFL-specific implementation
    pass
```

### 2.4 Type Hints Inconsistency

**Issues:**
- Some functions have type hints, others don't
- Inconsistent use of `Any` type
- Missing return type annotations

**Examples:**
```python
# Good:
def _to_int(value: Any) -> int:
    ...

# Missing types:
def _format_start_time(ts):  # No type hints
    ...

# Inconsistent:
def get_scoreboard() -> Dict[str, Any]:  # Too generic
    ...
```

**Recommendation:** Add comprehensive type hints throughout

---

## 3. ARCHITECTURE ISSUES

### 3.1 Tight Coupling Between UI and Backend

**Location:** `scoresource/ui/window.py` (5000+ lines)

**Issues:**
- UI directly calls backend methods
- Business logic mixed with presentation
- Difficult to test UI components
- Hard to swap backends

**Recommendation:** Implement proper separation:
```
UI Layer (PySide6)
    ↓
Presentation Layer (ViewModels)
    ↓
Business Logic Layer (Services)
    ↓
Data Access Layer (Repositories)
    ↓
External APIs
```

### 3.2 Global State Management

**Issues:**
```python
# From nfl.py:
_logo_cache: Dict[Tuple[str, str], bytes | None] = {}
_session = requests.Session()
_boxscore_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_roster_cache: Dict[str, Tuple[float, Dict[str, str]]] = {}
```

**Problems:**
- Global mutable state
- Thread safety concerns
- Testing difficulties
- Memory leaks potential

**Recommendation:** Use dependency injection and proper state management

### 3.3 Missing Abstraction Layers

**Issues:**
- Direct ESPN API calls throughout code
- No repository pattern
- No service layer
- Difficult to mock for testing

**Recommendation:** Implement repository pattern:
```python
class GameRepository:
    def get_live_games(self, sport: str) -> List[Game]:
        pass
    
    def get_game_details(self, game_id: str) -> GameDetails:
        pass

class ESPNGameRepository(GameRepository):
    # ESPN-specific implementation
    pass
```

---

## 4. PERFORMANCE ISSUES

### 4.1 Inefficient Caching Strategy

**Location:** Multiple cache dictionaries across modules

**Issues:**
- No cache size limits (memory leak risk)
- No LRU eviction
- Manual TTL checking
- Duplicate caching logic

**Recommendation:** Use proper caching library:
```python
from functools import lru_cache
from cachetools import TTLCache

# Instead of manual caching:
logo_cache = TTLCache(maxsize=100, ttl=3600)
```

### 4.2 Blocking API Calls in UI Thread

**Location:** `scoresource/ui/window.py`

**Issues:**
```python
# Some API calls may block UI
def refresh_scores(self):
    # This could freeze the UI
    data = self.backend.fetch_scoreboard()
```

**Recommendation:** Ensure all network calls use ThreadPoolExecutor (already partially implemented, needs consistency)

### 4.3 Redundant Data Processing

**Issues:**
- Same data parsed multiple times
- Repeated color calculations
- Unnecessary string operations in loops

**Example from nfl.py:**
```python
# Called repeatedly in loops:
def _normalize_match_tricode(tricode: Any) -> str:
    tri = str(tricode or "").upper()
    aliases = {
        "JAC": "JAX",
        # ... repeated dict creation
    }
    return aliases.get(tri, tri)
```

**Recommendation:** Cache computed values, move constants outside functions

---

## 5. TESTING GAPS

### 5.1 Minimal Test Coverage

**Current State:**
- Only `test_backends.py` and `test_logic.py` exist
- Tests are basic smoke tests
- No unit tests for individual functions
- No integration tests
- No UI tests

**Missing Tests:**
- Data parsing functions
- Cache management
- Error handling paths
- Edge cases (empty data, malformed responses)
- UI component behavior
- Real-time updates

### 5.2 No Mocking Infrastructure

**Issues:**
- Tests make real API calls
- Slow test execution
- Tests fail when APIs are down
- No test fixtures

**Recommendation:** Implement proper mocking:
```python
import pytest
from unittest.mock import Mock, patch

@pytest.fixture
def mock_espn_response():
    return {
        "games": [...],
        "lines": [...]
    }

def test_parse_scoreboard(mock_espn_response):
    with patch('requests.get') as mock_get:
        mock_get.return_value.json.return_value = mock_espn_response
        result = fetch_scoreboard()
        assert len(result['games']) > 0
```

---

## 6. DOCUMENTATION ISSUES

### 6.1 Missing Documentation

**Gaps:**
- No API documentation
- No architecture diagrams
- No contribution guidelines
- Minimal inline comments
- No docstrings for complex functions

**Needed:**
- Architecture overview
- Setup instructions (beyond basic README)
- API endpoint documentation
- Code style guide
- Troubleshooting guide

### 6.2 Unclear Function Purposes

**Examples:**
```python
# From nfl.py - what does this do?
def _coerce_state(state, status_text, clock, period):
    # 30 lines of logic with no explanation
    ...

# What's the difference between these?
def _format_start_time(ts):
    ...

def format_start_time(ts, timezone):
    ...
```

**Recommendation:** Add comprehensive docstrings:
```python
def _coerce_state(
    state: str | None,
    status_text: str | None,
    clock: str | None,
    period: int | None
) -> str | None:
    """
    Determine the actual game state by analyzing multiple indicators.
    
    ESPN's API sometimes provides inconsistent state information. This
    function reconciles the official state with clock/period data to
    determine the true game state.
    
    Args:
        state: Official game state from API ('pre', 'in', 'post')
        status_text: Human-readable status text
        clock: Game clock value
        period: Current period/quarter
        
    Returns:
        Normalized state string or None if indeterminate
        
    Examples:
        >>> _coerce_state('pre', 'Q1 12:00', '12:00', 1)
        'in'  # Game has started despite 'pre' state
    """
```

---

## 7. FEATURE COMPLETENESS

### 7.1 Incomplete Sport Support

**Issues:**
- MLB, MLS, NCAA Football have basic implementations
- Missing advanced stats for some sports
- Inconsistent feature parity across sports

**Gaps:**
- MLB: No pitch-by-pitch data
- MLS: Limited player stats
- NCAA Football: No conference standings

### 7.2 Missing User Features

**Requested Features (based on code structure):**
- [ ] Favorite teams
- [ ] Game notifications
- [ ] Historical game data
- [ ] Player comparison tools
- [ ] Custom themes
- [ ] Multi-game view
- [ ] Export game data

### 7.3 Configuration Limitations

**Issues:**
```python
# Hardcoded in code:
DEFAULT_SPORT = "NBA"
WINDOW_SIZE = (1280, 400)
REFRESH_INTERVAL = 30_000  # milliseconds
```

**Recommendation:** Create configuration file:
```yaml
# config.yaml
app:
  default_sport: NBA
  window:
    width: 1280
    height: 400
  refresh_interval: 30000
  
sports:
  nba:
    enabled: true
    api_timeout: 8.0
  nfl:
    enabled: true
    api_timeout: 8.0
```

---

## 8. SECURITY CONCERNS

### 8.1 No API Key Management

**Issues:**
- No authentication for APIs (currently using public endpoints)
- No rate limiting
- No API key rotation

**Recommendation:** Prepare for future API key requirements:
```python
# Use environment variables or secure storage
import os
from pathlib import Path

API_KEY = os.getenv('ESPN_API_KEY')
if not API_KEY:
    # Load from secure config
    config_path = Path.home() / '.scoresource' / 'credentials.json'
    # ...
```

### 8.2 Unsafe Data Handling

**Issues:**
```python
# From ui.py - potential XSS if data contains HTML
label.setText(team_name)  # No sanitization

# From nfl.py - eval-like behavior
try:
    return int(float(val))  # Could fail on malicious input
except:
    return 0
```

**Recommendation:** Validate and sanitize all external data

---

## 9. MAINTAINABILITY ISSUES

### 9.1 Complex Functions

**Examples:**
- `apply_boxscore()` in ui.py: 200+ lines
- `get_boxscore()` in nfl.py: 150+ lines
- `_fill_nfl_table()`: 100+ lines

**Recommendation:** Break down into smaller, focused functions

### 9.2 Inconsistent Naming Conventions

**Issues:**
```python
# Mix of conventions:
_private_function()  # Leading underscore
__very_private()     # Double underscore
public_function()    # No prefix
CONSTANT_VALUE       # All caps
_PRIVATE_CONSTANT    # Underscore + caps
```

**Recommendation:** Standardize naming:
- `_private_function()` for internal use
- `public_function()` for API
- `CONSTANT` for module-level constants
- `_INTERNAL_CONSTANT` for private constants

### 9.3 Dead Code

**Found:**
- Commented-out code blocks
- Unused imports
- Deprecated functions still present

**Recommendation:** Clean up or document why code is kept

---

## 10. DEPENDENCY MANAGEMENT

### 10.1 Minimal Dependencies

**Current:** Only 3 dependencies
```
PySide6
requests
websockets
```

**Missing Useful Libraries:**
- `python-dotenv` - Environment variable management
- `pydantic` - Data validation
- `pytest` - Better testing
- `black` - Code formatting
- `mypy` - Type checking
- `ruff` - Fast linting

### 10.2 No Version Pinning

**Issue:** `requirements.txt` has no version constraints

**Risk:** Breaking changes in dependencies

**Recommendation:**
```
PySide6>=6.6.0,<7.0.0
requests>=2.31.0,<3.0.0
websockets>=12.0,<13.0
```

---

## PRIORITY RECOMMENDATIONS

### Immediate (Week 1):
1. ✅ Fix real-time WebSocket implementation or disable feature
2. ✅ Add proper error logging throughout
3. ✅ Implement cache size limits to prevent memory leaks
4. ✅ Add comprehensive docstrings to complex functions

### Short-term (Month 1):
1. ✅ Refactor NFL module into smaller files
2. ✅ Standardize error handling patterns
3. ✅ Add unit tests for core functions
4. ✅ Create configuration file system
5. ✅ Document architecture and setup

### Medium-term (Quarter 1):
1. ✅ Implement proper separation of concerns (MVC/MVVM)
2. ✅ Create base classes for sport modules
3. ✅ Add integration tests
4. ✅ Implement proper caching strategy
5. ✅ Add user-requested features

### Long-term (Year 1):
1. ✅ Complete feature parity across all sports
2. ✅ Implement advanced analytics
3. ✅ Add mobile/web version
4. ✅ Create plugin system for custom sports
5. ✅ Performance optimization and profiling

---

## CONCLUSION

ScoreSource is a functional multi-sport scoreboard application with a solid foundation. However, it needs significant improvements in:

1. **Code Organization** - Reduce complexity, improve modularity
2. **Error Handling** - Add logging, better error messages
3. **Testing** - Comprehensive test coverage
4. **Documentation** - Better inline docs and architecture guides
5. **Performance** - Optimize caching and data processing
6. **Features** - Complete real-time support, add user-requested features

The codebase shows good understanding of the problem domain but would benefit from applying software engineering best practices more consistently.

**Estimated Effort:**
- Critical fixes: 2-3 weeks
- Code quality improvements: 1-2 months
- Architecture refactoring: 2-3 months
- Feature completion: 3-6 months

**Risk Level:** Medium
- Application works but has technical debt
- Real-time feature is non-functional
- Potential memory leaks from unbounded caches
- Difficult to maintain as complexity grows
