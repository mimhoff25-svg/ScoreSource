from __future__ import annotations

import time
from collections import OrderedDict
from typing import Generic, Iterator, MutableMapping, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(MutableMapping[K, V], Generic[K, V]):
    """
    Lightweight cachetools.TTLCache-compatible fallback.

    Supports the subset of behavior this project needs:
    - get/set/delete by key
    - membership checks that honor expiration
    - maxsize eviction of oldest items
    """

    def __init__(self, maxsize: int, ttl: float) -> None:
        self.maxsize = max(1, int(maxsize))
        self.ttl = float(ttl)
        self._store: "OrderedDict[K, tuple[float, V]]" = OrderedDict()

    def _expire(self) -> None:
        if not self._store:
            return
        now = time.monotonic()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self.ttl]
        for key in expired:
            self._store.pop(key, None)

    def __getitem__(self, key: K) -> V:
        self._expire()
        ts, value = self._store[key]
        if time.monotonic() - ts > self.ttl:
            self._store.pop(key, None)
            raise KeyError(key)
        self._store.move_to_end(key)
        return value

    def __setitem__(self, key: K, value: V) -> None:
        self._expire()
        self._store[key] = (time.monotonic(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def __delitem__(self, key: K) -> None:
        del self._store[key]

    def __iter__(self) -> Iterator[K]:
        self._expire()
        return iter(self._store.keys())

    def __len__(self) -> int:
        self._expire()
        return len(self._store)

    def __contains__(self, key: object) -> bool:
        self._expire()
        if key not in self._store:
            return False
        ts, _ = self._store[key]  # type: ignore[index]
        if time.monotonic() - ts > self.ttl:
            self._store.pop(key, None)  # type: ignore[arg-type]
            return False
        return True

    def clear(self) -> None:
        self._store.clear()


try:
    from cachetools import TTLCache as _CachetoolsTTLCache

    TTLCache = _CachetoolsTTLCache  # type: ignore[assignment]
except Exception:
    pass
