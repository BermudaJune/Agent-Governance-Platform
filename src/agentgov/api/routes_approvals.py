from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.storage.db import connect
from agentgov.storage.models import RunRecord, SessionRecord, now_iso
from agentgov.storage.repositories import Repository
from agentgov.runtime.run_service import RunService
from agentgov.runtime.dynamic_governance import DynamicGovernanceService


class DecideApprovalRequest(BaseModel):
    approved: bool
    approver_id: str = "operator"
    reason: str | None = None


class DemoApprovalRequest(BaseModel):
    title: str = "高风险工具调用审批"
    requested_by: str = "execution"
    reason: str = "Execution Agent 尝试执行写入型工具动作，需要人工审批"


def router(repo: Repository, run_service: RunService | None = None, config_path: str | None = None) -> APIRouter:
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
        rows = repo.query_all("approvals", "WHERE id = ?", (approval_id,))
        if not rows:
            raise HTTPException(status_code=404, detail="审批不存在，请刷新列表")
        approval = rows[0]
        if approval.get("action_summary", {}).get("type") == "delegation":
            if not config_path:
                raise HTTPException(status_code=503, detail="扩展审批服务未配置")
            try:
                result = DynamicGovernanceService(repo, config_path).decide(
                    approval["action_summary"]["request_id"], req.approved, req.approver_id, req.reason)
                return {"approval_id": approval_id, "status": status, **result}
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="扩展请求不存在") from exc
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        if approval["status"] != "pending":
            if approval["status"] == status:
                return {"approval_id": approval_id, "status": status, "already_decided": True}
            raise HTTPException(status_code=409, detail="此审批已处理或过期，请刷新")
        run = repo.get_run(approval["run_id"])
        node = repo.get_task_node_for_run(approval["run_id"])
        if node and node["status"] in {"superseded", "stale", "needs_replan"}:
            raise HTTPException(status_code=409, detail="任务已变更，此审批已过期")
        with connect(repo.database) as conn:
            updated = conn.execute(
                "UPDATE approvals SET status = ?, approver_id = ?, reason = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
                (status, req.approver_id, req.reason, now_iso(), approval_id),
            )
            if updated.rowcount != 1:
                raise HTTPException(status_code=409, detail="审批状态已更新，请刷新")
            conn.commit()
        if not req.approved:
            if run:
                repo.update_run_status(approval["run_id"], "rejected", error=req.reason or "approval rejected")
                if run_service:
                    run_service.planning.after_run_execute(run["id"], "failed", {"error": req.reason or "approval rejected"})
                repo.update_session_status(run["session_id"], "failed", req.reason or "工具审批被拒绝，可向 Leader 调整方案")
            return {"approval_id": approval_id, "status": status, "run_status": "rejected"}
        if run and run["status"] in {"paused", "awaiting_approval"} and run_service is not None:
            resumed = run_service.resume_run(run["id"], execute_now=True)
            return {"approval_id": approval_id, "status": status, "run_status": resumed.get("status"), "execution": resumed}
        return {"approval_id": approval_id, "status": status, "run_status": run.get("status") if run else None}

    return r
