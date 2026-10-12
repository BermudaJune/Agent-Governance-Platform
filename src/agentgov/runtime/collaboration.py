from __future__ import annotations

from agentgov.event_stream.stream import EventStream
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class CollaborationRuntime:
    def __init__(self, repo: Repository, events: EventStream):
        self.repo = repo
        self.events = events

    def assign_task(self, session_id: str, parent_run_id: str, from_agent: str, to_agent: str, instruction: str, strategy: str) -> dict:
        message_id = self.repo.insert_generic(
            "agent_messages",
            {
                "trace_id": parent_run_id,
                "session_id": session_id,
                "parent_run_id": parent_run_id,
                "source_agent_id": from_agent,
                "target_agent_id": to_agent,
                "message_type": "task.assigned",
                "payload": {"strategy": strategy, "instruction": instruction},
                "status": "sent",
                "created_at": now_iso(),
            },
        )
        self.events.append(parent_run_id, session_id, "agent.message.sent", "agent", from_agent, "completed", {"message_id": message_id, "to": to_agent})
        return {"message_id": message_id}

    def submit_result(self, session_id: str, parent_run_id: str, from_agent: str, to_agent: str, child_run_id: str, result: dict) -> dict:
        message_id = self.repo.insert_generic(
            "agent_messages",
            {
                "trace_id": parent_run_id,
                "session_id": session_id,
                "parent_run_id": parent_run_id,
                "source_agent_id": from_agent,
                "target_agent_id": to_agent,
                "message_type": "task.result",
                "payload": {"child_run_id": child_run_id, "status": result.get("status"), "summary": result.get("response", "")[:500]},
                "status": "sent",
                "created_at": now_iso(),
            },
        )
        self.events.append(parent_run_id, session_id, "agent.result.sent", "agent", from_agent, "completed", {"message_id": message_id, "to": to_agent})
        return {"message_id": message_id}
