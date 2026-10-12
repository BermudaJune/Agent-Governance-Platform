from __future__ import annotations

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class MemoryStore:
    def __init__(self, repo: Repository):
        self.repo = repo

    def commit(self, content: str, source_run_id: str, evidence_refs: list[str], agent_id: str | None = None) -> str:
        return self.repo.insert_generic(
            "memory_items",
            {
                "agent_id": agent_id,
                "content": content,
                "source_run_id": source_run_id,
                "source_evidence_refs": evidence_refs,
                "status": "active",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )

    def search(self, query: str) -> list[dict]:
        return [row for row in self.repo.query_all("memory_items") if query.lower() in row.get("content", "").lower()]
