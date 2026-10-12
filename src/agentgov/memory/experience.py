from __future__ import annotations

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class ExperienceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def generate(self, run_id: str, summary: str, evidence_refs: list[str] | None = None) -> str:
        return self.repo.insert_generic(
            "experience_candidates",
            {
                "source_run_id": run_id,
                "summary": summary,
                "evidence_refs": evidence_refs or [],
                "confidence": 0.7,
                "status": "pending",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )
