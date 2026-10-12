from __future__ import annotations

from typing import Any

from agentgov.storage.repositories import Repository


class EventStream:
    def __init__(self, repo: Repository):
        self.repo = repo

    def append(
        self,
        run_id: str,
        session_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        status: str = "completed",
        payload: dict[str, Any] | None = None,
    ):
        return self.repo.append_step(run_id, session_id, event_type, actor_type, actor_id, status, payload or {})

    def list_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return self.repo.list_steps(run_id)
