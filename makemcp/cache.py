"""Tiny TTL cache with LRU bound (stdlib only, lock-free fast path)."""
from __future__ import annotations

import time
from collections import OrderedDict


class TTLCache:
    def __init__(self, maxsize: int = 1024, ttl: float = 60.0):
        self.maxsize = maxsize
        self.ttl = ttl
        self._d: OrderedDict = OrderedDict()

    def get(self, key):
        try:
            exp, val = self._d[key]
        except KeyError:
            return None, False
        if exp < time.monotonic():
            try:
                del self._d[key]
            except KeyError:
                pass
            return None, False
        self._d.move_to_end(key)
        return val, True

    def set(self, key, value, ttl: float | None = None):
        exp = time.monotonic() + (self.ttl if ttl is None else ttl)
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = (exp, value)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)

    def clear(self):
        self._d.clear()
