from __future__ import annotations

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class TeamBus:
    def __init__(self, repo: Repository):
        self.repo = repo

    def publish(self, trace_id: str, session_id: str, source: str, target: str, message_type: str, payload: dict, parent_run_id: str | None = None) -> str:
        return self.repo.insert_generic(
            "agent_messages",
            {
                "trace_id": trace_id,
                "session_id": session_id,
                "parent_run_id": parent_run_id,
                "source_agent_id": source,
                "target_agent_id": target,
                "message_type": message_type,
                "payload": payload,
                "status": "sent",
                "created_at": now_iso(),
            },
        )
