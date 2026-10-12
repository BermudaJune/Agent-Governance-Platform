from __future__ import annotations


ALLOWED_TRANSITIONS = {
    "pending": {"running", "paused", "cancelled", "failed"},
    "running": {"awaiting_approval", "awaiting_budget", "paused", "completed", "failed", "timeout", "cancelled"},
    "awaiting_approval": {"running", "paused", "rejected", "failed", "cancelled"},
    "awaiting_budget": {"running", "paused", "failed", "cancelled"},
    "paused": {"pending", "running", "cancelled"},
    "completed": set(),
    "failed": set(),
    "rejected": set(),
    "cancelled": set(),
    "timeout": set(),
}


class InvalidTransition(ValueError):
    pass


def ensure_transition(current: str, next_status: str) -> None:
    if next_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidTransition(f"invalid run status transition: {current} -> {next_status}")
