from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.storage.models import RunRecord
from agentgov.storage.repositories import Repository
from agentgov.runtime.run_service import RunService


class CreateRunRequest(BaseModel):
    session_id: str
    agent_id: str
    input_summary: str
    parent_run_id: str | None = None


class RunControlRequest(BaseModel):
    reason: str = "operator action"
    execute_now: bool = False


def router(repo: Repository, run_service: RunService | None = None) -> APIRouter:
    r = APIRouter(prefix="/runs", tags=["runs"])

    @r.post("")
    def create_run(req: CreateRunRequest):
        run = repo.create_run(RunRecord(**req.model_dump()))
        repo.append_step(run.id, run.session_id, "run.started", "agent", run.agent_id, "started", {"input": run.input_summary})
        return run.__dict__

    @r.get("")
    def list_runs():
        return repo.list_runs()

    @r.get("/{run_id}")
    def get_run(run_id: str):
        return {"run": repo.get_run(run_id), "steps": repo.list_steps(run_id)}

    @r.get("/{run_id}/events")
    def get_events(run_id: str):
        return repo.list_steps(run_id)

    @r.post("/{run_id}/execute")
    def execute_run(run_id: str):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        return run_service.execute(run_id)

    @r.post("/{run_id}/pause")
    def pause_run(run_id: str, req: RunControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        try:
            return run_service.pause_run(run_id, req.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown run: {run_id}") from exc

    @r.post("/{run_id}/cancel")
    def cancel_run(run_id: str, req: RunControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        try:
            return run_service.cancel_run(run_id, req.reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown run: {run_id}") from exc

    @r.post("/{run_id}/resume")
    def resume_run(run_id: str, req: RunControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        try:
            return run_service.resume_run(run_id, req.execute_now)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown run: {run_id}") from exc

    @r.post("/{run_id}/retry")
    def retry_run(run_id: str, req: RunControlRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        try:
            return run_service.retry_run(run_id, req.execute_now)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown run: {run_id}") from exc

    return r
