from __future__ import annotations

from agentgov.storage.repositories import Repository


class EvidenceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def add(self, run_id: str, ref_type: str, ref_id: str, summary: str, step_id: str | None = None, path: str | None = None) -> str:
        return self.repo.insert_generic(
            "evidence_refs",
            {"ref_type": ref_type, "ref_id": ref_id, "run_id": run_id, "step_id": step_id, "path": path, "summary": summary},
        )
