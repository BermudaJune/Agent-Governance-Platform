from __future__ import annotations

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class ReasoningTraceService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def record(self, run_id: str, agent_id: str, decision_summary: str, evidence_refs: list[str], confidence: float = 0.5) -> str:
        return self.repo.insert_generic(
            "reasoning_traces",
            {
                "run_id": run_id,
                "agent_id": agent_id,
                "decision_summary": decision_summary,
                "evidence_refs": evidence_refs,
                "alternatives_considered": [],
                "confidence": confidence,
                "risk_flags": [],
                "created_at": now_iso(),
            },
        )
