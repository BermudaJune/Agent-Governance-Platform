from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agentgov.storage.db import connect
from agentgov.storage.models import RunRecord, SessionRecord, now_iso
from agentgov.storage.repositories import Repository


class DecideApprovalRequest(BaseModel):
    approved: bool
    approver_id: str = "operator"
    reason: str | None = None


class DemoApprovalRequest(BaseModel):
    title: str = "高风险工具调用审批"
    requested_by: str = "execution"
    reason: str = "Execution Agent 尝试执行写入型工具动作，需要人工审批"


def router(repo: Repository) -> APIRouter:
    r = APIRouter(prefix="/approvals", tags=["approvals"])

    @r.get("")
    def list_approvals():
        return repo.query_all("approvals", "ORDER BY created_at DESC")

    @r.post("/demo")
    def create_demo_approval(req: DemoApprovalRequest):
        session = repo.create_session(
            SessionRecord(
                title=req.title,
                owner_id="operator",
                root_agent_id="execution",
                status="awaiting_approval",
            )
        )
        run = repo.create_run(
            RunRecord(
                session_id=session.id,
                agent_id="execution",
                input_summary=req.reason,
                status="awaiting_approval",
                started_at=now_iso(),
            )
        )
        repo.append_step(run.id, session.id, "run.started", "agent", "execution", "started", {"input": req.reason})
        step = repo.append_step(
            run.id,
            session.id,
            "approval.requested",
            "system",
            req.requested_by,
            "waiting",
            {"risk": "write_tool", "reason": req.reason},
        )
        approval_id = repo.insert_generic(
            "approvals",
            {
                "run_id": run.id,
                "step_id": step.id,
                "requested_by": req.requested_by,
                "status": "pending",
                "action_summary": {"risk": "write_tool", "reason": req.reason},
                "created_at": now_iso(),
            },
        )
        return {"approval_id": approval_id, "run_id": run.id, "session_id": session.id, "status": "pending"}

    @r.post("/{approval_id}/decide")
    def decide(approval_id: str, req: DecideApprovalRequest):
        status = "approved" if req.approved else "rejected"
        with connect(repo.database) as conn:
            row = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
            if row is None:
                return {"status": "missing"}
            conn.execute(
                "UPDATE approvals SET status = ?, approver_id = ?, reason = ?, decided_at = ? WHERE id = ?",
                (status, req.approver_id, req.reason, now_iso(), approval_id),
            )
            conn.commit()
        return {"approval_id": approval_id, "status": status}

    return r
