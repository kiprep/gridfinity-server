from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock


class LRUCache:
    """In-memory LRU cache for STL bytes.

    Gridfinity STLs are typically 200KB-2MB.
    100 entries ~= 200MB worst case. Fine for local dev.
    """

    def __init__(self, max_entries: int = 100, ttl_seconds: int = 3600):
        self._cache: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
        self._max = max_entries
        self._ttl = ttl_seconds
        self._lock = Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            if key not in self._cache:
                return None
            ts, data = self._cache[key]
            if time.time() - ts > self._ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return data

    def set(self, key: str, data: bytes) -> None:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (time.time(), data)
            while len(self._cache) > self._max:
                self._cache.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


stl_cache = LRUCache()
