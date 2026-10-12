from __future__ import annotations


class DbBackedRateLimiter:
    def __init__(self):
        self.counts: dict[str, int] = {}

    def allow(self, key: str, limit: int) -> bool:
        current = self.counts.get(key, 0)
        if current >= limit:
            return False
        self.counts[key] = current + 1
        return True
