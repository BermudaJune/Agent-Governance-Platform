from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.dashboard.audit_query import audit_events
from agentgov.dashboard.service import DashboardService
from agentgov.dashboard.topology import session_graph, team_graph, topology
from agentgov.storage.repositories import Repository
from agentgov.storage.models import now_iso
from agentgov.runtime.dynamic_governance import DynamicGovernanceService


class EvolutionDecision(BaseModel):
    status: str
    reason: str = "operator decision"


def router(repo: Repository, config_path: str = "config/examples/local.scripted.yaml") -> APIRouter:
    r = APIRouter(prefix="/dashboard", tags=["dashboard"])
    service = DashboardService(repo, config_path)

    @r.get("/overview")
    def overview():
        return service.overview()

    @r.get("/workbench")
    def workbench():
        return service.workbench()

    @r.get("/evolution")
    def evolution():
        candidates = repo.query_all("experience_candidates", "ORDER BY updated_at DESC")
        return {
            "candidates": candidates,
            "counts": {
                "pending": len([item for item in candidates if item.get("status") == "pending"]),
                "approved": len([item for item in candidates if item.get("status") == "approved"]),
                "rejected": len([item for item in candidates if item.get("status") == "rejected"]),
            },
            "pipeline": ["候选", "证据复核", "评测", "人工审批", "版本发布", "可回滚"],
            "evaluation_available": False,
            "publishing_available": False,
        }

    @r.post("/evolution/candidates/{candidate_id}/decision")
    def decide_evolution(candidate_id: str, req: EvolutionDecision):
        if req.status not in {"approved", "rejected", "evaluating"}:
            raise HTTPException(status_code=400, detail="status must be approved, rejected or evaluating")
        rows = repo.query_all("experience_candidates", "WHERE id = ?", (candidate_id,))
        if not rows:
            raise HTTPException(status_code=404, detail=f"unknown experience candidate: {candidate_id}")
        if req.status in {"approved", "evaluating"}:
            raise HTTPException(status_code=409, detail="真实回归评估和版本发布尚未接通，候选仅供复核，不允许标记为已评估或发布")
        repo.update_generic("experience_candidates", candidate_id, {"status": req.status, "updated_at": now_iso()})
        return {**(repo.query_all("experience_candidates", "WHERE id = ?", (candidate_id,))[0]), "decision_reason": req.reason}

    @r.get("/runs/{run_id}")
    def run_detail(run_id: str):
        return service.run_detail(run_id)

    @r.get("/sessions/{session_id}")
    def session_detail(session_id: str):
        return service.session_detail(session_id)

    @r.get("/sessions/{session_id}/audit-report")
    def session_audit_report(session_id: str):
        return service.session_audit_report(session_id)

    @r.get("/sessions/{session_id}/available-actions")
    def session_available_actions(session_id: str):
        return service.session_available_actions(session_id)

    @r.get("/runs/{run_id}/available-actions")
    def run_available_actions(run_id: str):
        return service.run_available_actions(run_id)

    @r.get("/agents/{agent_id}")
    def agent_detail(agent_id: str):
        return service.agent_detail(agent_id)

    @r.get("/topology")
    def get_topology():
        return topology(repo)

    @r.get("/topology/sessions/{session_id}")
    def get_session_topology(session_id: str, current_only: bool = False):
        DynamicGovernanceService(repo, config_path).ensure_root(session_id)
        return session_graph(repo, session_id, current_only=current_only)

    @r.get("/topology/teams")
    def get_team_topology(team_id: str | None = None):
        return team_graph(config_path, team_id)

    @r.get("/queue")
    def queue():
        return service.queue()

    @r.get("/security")
    def security():
        return service.security()

    @r.get("/audit")
    def audit(run_id: str | None = None):
        return audit_events(repo, run_id)

    return r
