# ScoreScource Code Quality Improvements - TODO List

## Phase 1: Critical Fixes (Week 1)

### 1.1 Consolidate NFL Modules
- [ ] Remove duplicate scoresource/nfl.py (keep sports/nfl.py as main)
- [ ] Update imports in registry.py to use sports/ modules
- [ ] Update imports in logic.py to use sports/ modules
- [ ] Remove old nfl.py file

### 1.2 Add Cache Size Limits
- [ ] Add TTLCache with maxsize to scoresource/sports/nfl.py
- [ ] Add TTLCache with maxsize to all sport backends
- [ ] Add cachetools to requirements.txt

### 1.3 Add Proper Error Logging
- [ ] Add logging to all API calls in sport backends
- [ ] Add logging to cache operations
- [ ] Add context to error messages

## Phase 2: Code Quality (Month 1)

### 2.1 Standardize Error Handling
- [ ] Create standard error handling pattern
- [ ] Apply consistent pattern to all backends
- [ ] Add Result type or consistent return types

### 2.2 Document Magic Numbers
- [ ] Add constants with documentation for TTL values
- [ ] Add constants for timeout values
- [ ] Add comments explaining time-based constants

### 2.3 Fix Inconsistent Type Hints
- [ ] Add return types to all functions missing them
- [ ] Standardize Dict/Any usage
- [ ] Run mypy for type checking

## Phase 3: Testing (Month 1)

### 3.1 Add Unit Tests
- [ ] Test data parsing functions
- [ ] Test cache management
- [ ] Test error handling paths
- [ ] Test edge cases

### 3.2 Add Mocking Infrastructure
- [ ] Create pytest fixtures for API responses
- [ ] Add mock for requests.Session
- [ ] Add test for offline mode

## Phase 4: Architecture (Quarter 1)

### 4.1 Refactor UI Module
- [ ] Extract team display components
- [ ] Extract clock/timer components
- [ ] Extract table components
- [ ] Extract sport-specific panels

### 4.2 Add Dependency Injection
- [ ] Create service layer
- [ ] Add repository pattern for data access
- [ ] Implement proper state management

## Implementation Progress
- [x] Created TODO list
- [ ] Started Phase 1 implementation

