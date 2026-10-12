from __future__ import annotations

from agentgov.storage.repositories import Repository


def audit_events(repo: Repository, run_id: str | None = None) -> list[dict]:
    if run_id:
        return repo.list_steps(run_id)
    return repo.query_all("run_steps", "ORDER BY created_at DESC")
