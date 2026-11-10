"""Tiny process-local TTL cache for slow-changing aggregates (freshness).

The web prototype calls /api/v1/freshness for the retailer directory and
home-page freshness panel. A short TTL (default 60 s) keeps the pages snappy
without adding any new infrastructure. Values are returned as-is; callers must
treat them as immutable snapshots.
"""

import threading
import time
from typing import Any


class TtlCache:
    def __init__(self, ttl_seconds: float = 60.0):
        self._ttl = ttl_seconds
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_load(self, key: str, loader):
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] > now:
                return entry[1]
        value = loader()
        with self._lock:
            self._entries[key] = (time.monotonic() + self._ttl, value)
        return value

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
