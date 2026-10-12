from __future__ import annotations


def health_score(success_rate: float, error_count: int) -> int:
    return max(0, min(100, int(success_rate * 100) - error_count * 5))
