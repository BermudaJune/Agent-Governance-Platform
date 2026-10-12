from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.storage.models import SessionRecord
from agentgov.storage.repositories import Repository
from agentgov.runtime.run_service import RunService


class CreateSessionRequest(BaseModel):
    title: str
    owner_id: str = "local"
    root_agent_id: str | None = None
    team_id: str | None = None


class SessionControlRequest(BaseModel):
    reason: str = "operator action"
    execute_now: bool = False


def router(repo: Repository, run_service: RunService | None = None) -> APIRouter:
    r = APIRouter(prefix="/sessions", tags=["sessions"])

    @r.post("")
    def create_session(req: CreateSessionRequest):
        return repo.create_session(SessionRecord(**req.model_dump())).__dict__

    @r.get("")
    def list_sessions():
        return repo.list_sessions()

    @r.get("/{session_id}")
    def get_session(session_id: str):
        return {
            "session": repo.get_session(session_id),
            "runs": repo.list_runs_for_session(session_id),
            "steps": repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "messages": repo.query_all("agent_messages", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "evidence_refs": repo.query_all(
                "evidence_refs",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY id",
                (session_id,),
            ),
        }

    @r.post("/{session_id}/pause")
    def pause_session(session_id: str, req: SessionControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return run_service.pause_session(session_id, req.reason)

    @r.post("/{session_id}/cancel")
    def cancel_session(session_id: str, req: SessionControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return run_service.cancel_session(session_id, req.reason)

    @r.post("/{session_id}/resume")
    def resume_session(session_id: str, req: SessionControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return run_service.resume_session(session_id, req.execute_now)

    @r.post("/{session_id}/execute-pending")
    def execute_pending(session_id: str):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return run_service.execute_session_pending(session_id)

    return r
