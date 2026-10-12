from __future__ import annotations

from agentgov.event_stream.stream import EventStream
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class ApprovalService:
    def __init__(self, repo: Repository, events: EventStream):
        self.repo = repo
        self.events = events

    def request(self, run_id: str, session_id: str, requested_by: str, action_summary: dict) -> str:
        step = self.events.append(run_id, session_id, "approval.requested", "system", requested_by, "waiting", action_summary)
        approval_id = self.repo.insert_generic(
            "approvals",
            {
                "run_id": run_id,
                "step_id": step.id,
                "requested_by": requested_by,
                "status": "pending",
                "action_summary": action_summary,
                "created_at": now_iso(),
            },
        )
        self.repo.update_run_status(run_id, "awaiting_approval")
        return approval_id

    def decide(self, approval_id: str, run_id: str, session_id: str, approver_id: str, approved: bool, reason: str | None = None) -> None:
        status = "approved" if approved else "rejected"
        with self.repo_query_conn() as conn:
            conn.execute(
                "UPDATE approvals SET status = ?, approver_id = ?, reason = ?, decided_at = ? WHERE id = ?",
                (status, approver_id, reason, now_iso(), approval_id),
            )
            conn.commit()
        self.events.append(run_id, session_id, "approval.decided", "user", approver_id, "completed", {"approval_id": approval_id, "status": status, "reason": reason})
        if not approved:
            self.repo.update_run_status(run_id, "rejected", error=reason or "approval rejected")
            self.events.append(run_id, session_id, "run.final", "system", "approval", "completed", {"status": "rejected"})

    def repo_query_conn(self):
        from agentgov.storage.db import connect

        return connect(self.repo.database)
