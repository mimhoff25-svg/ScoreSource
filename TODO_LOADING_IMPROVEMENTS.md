# Loading Improvements TODO

## Approved Plan
- Implement proper caching with cachetools.TTLCache
- Add asynchronous data fetching with asyncio/ThreadPoolExecutor
- Add loading indicators in UI
- Optimize data processing with computed value caching
- Update dependencies

## Steps
- [ ] Update requirements.txt: Add cachetools>=5.3.0
- [ ] Edit scoresource/nfl.py: Replace global caches with TTLCache
- [ ] Edit scoresource/logic.py: Add async fetching methods
- [ ] Edit scoresource/ui.py: Add loading states and async handling
- [ ] Optimize redundant processing in backends
- [ ] Test changes: Run app, check memory, responsiveness
