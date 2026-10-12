from __future__ import annotations

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class SpanService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def start(self, trace_id: str, run_id: str, span_type: str, name: str, parent_span_id: str | None = None) -> str:
        return self.repo.insert_generic(
            "span_records",
            {
                "trace_id": trace_id,
                "run_id": run_id,
                "parent_span_id": parent_span_id,
                "span_type": span_type,
                "name": name,
                "status": "started",
                "started_at": now_iso(),
                "attributes": {},
            },
        )
