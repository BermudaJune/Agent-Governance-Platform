from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agentgov.memory.cases import CaseConflict, SessionCaseService
from agentgov.storage.repositories import Repository


class SessionReviewRequest(BaseModel):
    snapshot_key: str = Field(min_length=64, max_length=64)
    outcome: Literal["accepted", "failed", "cancelled"] = "accepted"
    reviewer_id: str = "operator"
    notes: str = Field(default="", max_length=5000)
    satisfaction: int | None = Field(default=None, ge=1, le=5)
    reusable_guidance: str = Field(default="", max_length=1500)
    share_scope: Literal["private", "shared_methods"] = "private"
    tags: list[str] = Field(default_factory=list, max_length=12)
    proposal_target: Literal["leader_general", "task_strategy", "agent_template", "skill", "tool", "policy"] | None = None


class CaseSharingRequest(BaseModel):
    share_scope: Literal["private", "shared_methods"]
    actor_id: str = "operator"


def router(repo: Repository) -> APIRouter:
    r = APIRouter(tags=["session-memory"])
    service = SessionCaseService(repo)

    @r.get("/sessions/{session_id}/review")
    def review_state(session_id: str):
        try:
            return service.review_state(session_id)
        except KeyError as exc:
            raise HTTPException(404, "Session 不存在") from exc

    @r.post("/sessions/{session_id}/review")
    def archive(session_id: str, req: SessionReviewRequest):
        try:
            return service.archive(session_id, **req.model_dump())
        except KeyError as exc:
            raise HTTPException(404, "Session 不存在") from exc
        except CaseConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @r.get("/memory/cases")
    def list_cases(owner_id: str = "operator", q: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=100)):
        cases = repo.query_all("session_cases", "WHERE owner_id = ? ORDER BY created_at DESC LIMIT 500", (owner_id,))
        query = q.strip().lower()
        if query:
            cases = [case for case in cases if query in " ".join([
                case["case_data"].get("title", ""), " ".join(case["tags"]), case["reusable_guidance"], case["notes"],
            ]).lower()]
        return {"cases": cases[:limit]}

    @r.get("/memory/cases/{case_id}")
    def case_detail(case_id: str):
        rows = repo.query_all("session_cases", "WHERE id = ?", (case_id,))
        if not rows:
            raise HTTPException(404, "案例不存在")
        return rows[0]

    @r.post("/memory/cases/{case_id}/sharing")
    def set_sharing(case_id: str, req: CaseSharingRequest):
        try:
            return service.set_sharing(case_id, req.share_scope, req.actor_id)
        except KeyError as exc:
            raise HTTPException(404, "案例不存在") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    return r
