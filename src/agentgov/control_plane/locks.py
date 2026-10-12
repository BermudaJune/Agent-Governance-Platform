from __future__ import annotations

from contextlib import contextmanager


class SessionLock:
    def __init__(self):
        self._locked: set[str] = set()

    @contextmanager
    def acquire(self, session_id: str):
        if session_id in self._locked:
            raise RuntimeError(f"session is already write-locked: {session_id}")
        self._locked.add(session_id)
        try:
            yield
        finally:
            self._locked.remove(session_id)
