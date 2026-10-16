from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentgov.runtime.dynamic_governance import DynamicGovernanceService
from agentgov.storage.repositories import Repository
from agentgov.runtime.run_service import RunService


class DelegationRequest(BaseModel):
    parent_agent_id: str | None = None
    requester_agent_id: str | None = None
    requested_agent_id: str | None = None
    requested_role: str = "specialist"
    objective: str
    requested_skills: list[str] = Field(default_factory=list)
    requested_tools: list[str] = Field(default_factory=list)
    budget_usd: float = 0
    run_id: str | None = None
    reason: str | None = None
    auto_approve: bool = True


class DelegationDecision(BaseModel):
    approved: bool
    approver_id: str = "operator"
    reason: str | None = None


class CapabilityRequest(BaseModel):
    agent_id: str
    capability_id: str
    requester_agent_id: str | None = None


class RetirementRequest(BaseModel):
    actor_id: str = "operator"
    reason: str | None = None


def router(repo: Repository, config_path: str, run_service: RunService | None = None) -> APIRouter:
    r = APIRouter(tags=["runtime-governance"])
    service = DynamicGovernanceService(repo, config_path)

    def ensure_session(session_id: str) -> None:
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")

    @r.get("/sessions/{session_id}/agents")
    def session_agents(session_id: str):
        ensure_session(session_id)
        return service.list_agents(session_id)

    @r.get("/sessions/{session_id}/delegations")
    def session_delegations(session_id: str):
        ensure_session(session_id)
        return service.repo.list_delegation_requests(session_id)

    @r.get("/sessions/{session_id}/grants")
    def session_grants(session_id: str):
        ensure_session(session_id)
        return {
            "skills": service.repo.list_session_skill_grants(session_id),
            "tools": service.repo.list_session_tool_grants(session_id),
        }

    @r.post("/sessions/{session_id}/delegations")
    def create_delegation(session_id: str, req: DelegationRequest):
        ensure_session(session_id)
        try:
            return service.create_delegation(session_id, req.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.post("/delegations/{delegation_id}/decide")
    def decide_delegation(delegation_id: str, req: DelegationDecision):
        try:
            result = service.decide(delegation_id, req.approved, req.approver_id, req.reason)
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="扩展请求不存在，请刷新 Session") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @r.post("/sessions/{session_id}/agents/{agent_id}/retire")
    def retire_agent(session_id: str, agent_id: str, req: RetirementRequest):
        ensure_session(session_id)
        try:
            return service.retire(session_id, agent_id, req.actor_id, req.reason)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.post("/sessions/{session_id}/skills/{skill_id}/request")
    def request_skill(session_id: str, skill_id: str, req: CapabilityRequest):
        ensure_session(session_id)
        try:
            return service.request_capability(session_id, req.agent_id, "skill", skill_id, req.requester_agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @r.post("/sessions/{session_id}/tools/{tool_id}/request")
    def request_tool(session_id: str, tool_id: str, req: CapabilityRequest):
        ensure_session(session_id)
        try:
            return service.request_capability(session_id, req.agent_id, "tool", tool_id, req.requester_agent_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return r
