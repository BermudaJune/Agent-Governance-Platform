from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agentgov.knowledge.models import KnowledgePolicy, KnowledgeSourceInput
from agentgov.storage.models import SessionRecord
from agentgov.storage.repositories import Repository
from agentgov.runtime.run_service import RunService
from agentgov.runtime.dynamic_governance import DynamicGovernanceService


TEXT_PREVIEW_TYPES = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".json": "application/json",
    ".csv": "text/csv",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".log": "text/plain",
    ".py": "text/x-python",
}
IMAGE_PREVIEW_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class CreateSessionRequest(BaseModel):
    title: str
    owner_id: str = "local"
    root_agent_id: str | None = None
    team_id: str | None = None
    objective: str | None = None
    knowledge_sources: list[KnowledgeSourceInput] = Field(default_factory=list)
    knowledge_policy: KnowledgePolicy = Field(default_factory=KnowledgePolicy)


class SessionControlRequest(BaseModel):
    reason: str = "operator action"
    execute_now: bool = False


class CheckpointRequest(BaseModel):
    label: str = "手动检查点"
    reason: str = "operator checkpoint"


class RollbackRequest(BaseModel):
    checkpoint_id: str
    reason: str = "operator rollback"
    actor_id: str = "operator"


class SessionFeedbackRequest(BaseModel):
    target_type: Literal["session", "requirement", "action", "artifact", "agent"] = "session"
    target_id: str | None = None
    message: str = Field(min_length=1, max_length=20000)
    requested_action: Literal["replan", "record"] = "replan"
    created_by: str = "operator"
    reason_type: Literal["unspecified", "new_requirement", "misunderstanding", "execution_issue", "preference"] = "unspecified"


class PlanDecisionRequest(BaseModel):
    approved: bool
    approver_id: str = "operator"
    reason: str = ""
    plan_id: str | None = None


def router(
    repo: Repository,
    run_service: RunService | None = None,
    config_path: str | None = None,
    workspace_root: str | Path = ".",
) -> APIRouter:
    r = APIRouter(prefix="/sessions", tags=["sessions"])
    governance = DynamicGovernanceService(repo, config_path) if config_path else None

    def artifact_target(session_id: str, artifact_id: str) -> tuple[dict, Path]:
        rows = repo.query_all("artifacts", "WHERE id = ? AND session_id = ? LIMIT 1", (artifact_id, session_id))
        if not rows:
            raise HTTPException(status_code=404, detail="产物不存在或不属于此 Session")
        workspace = (Path(workspace_root) / "data" / "workspaces" / session_id).resolve()
        target = Path(rows[0]["path"]).resolve()
        try:
            target.relative_to(workspace)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="产物路径不在此 Session 工作区内") from exc
        if not target.is_file():
            raise HTTPException(status_code=404, detail="产物文件已不存在")
        return rows[0], target

    @r.post("")
    def create_session(req: CreateSessionRequest):
        payload = req.model_dump()
        sources = payload.pop("knowledge_sources", [])
        policy = payload.pop("knowledge_policy", {})
        if run_service:
            session = run_service.create_session(**payload, knowledge_sources=sources, knowledge_policy=policy)
        else:
            payload.pop("objective", None)
            payload["metadata"] = {"knowledge_policy": policy}
            session = repo.create_session(SessionRecord(**payload))
            for source in sources:
                repo.add_session_knowledge(session.id, source)
        if governance:
            governance.ensure_root(session.id)
        return repo.get_session(session.id)

    @r.get("")
    def list_sessions():
        return repo.list_sessions()

    @r.get("/{session_id}")
    def get_session(session_id: str):
        if governance:
            governance.ensure_root(session_id)
        return {
            "session": repo.get_session(session_id),
            "runs": repo.list_runs_for_session(session_id),
            "approvals": repo.query_all(
                "approvals",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at DESC",
                (session_id,),
            ),
            "steps": repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "messages": repo.query_all("agent_messages", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "plans": repo.list_plans_for_session(session_id),
            "task_nodes": repo.list_task_nodes_for_session(session_id),
            "task_edges": repo.list_task_edges_for_session(session_id),
            "evidence_refs": repo.query_all(
                "evidence_refs",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY id",
                (session_id,),
            ),
            "artifacts": repo.list_artifacts_for_session(session_id),
            "artifact_versions": repo.list_artifact_versions(session_id),
            "knowledge_sources": repo.list_session_knowledge(session_id),
            "knowledge_grants": repo.list_knowledge_grants(session_id),
            "knowledge_access_events": repo.query_all("knowledge_access_events", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "knowledge_policy": (repo.get_session(session_id) or {}).get("metadata", {}).get("knowledge_policy", {}),
            "session_agents": repo.list_session_agents(session_id),
            "delegation_requests": repo.list_delegation_requests(session_id),
            "skill_grants": repo.list_session_skill_grants(session_id),
            "tool_grants": repo.list_session_tool_grants(session_id),
            "agent_lifecycle_events": repo.list_agent_lifecycle_events(session_id),
            "checkpoints": repo.list_checkpoints(session_id),
            "rollback_events": repo.list_rollback_events(session_id),
            "requirements": repo.list_requirements_for_session(session_id),
            "current_requirement": repo.get_current_requirement(session_id),
            "feedback": repo.list_session_feedback(session_id),
            "replan_required": (repo.get_session(session_id) or {}).get("status") == "needs_replan",
            "affected_nodes": [
                node for node in repo.list_task_nodes_for_session(session_id)
                if node.get("status") in {"needs_replan", "stale"}
            ],
            "stale_artifacts": [
                artifact for artifact in repo.list_artifacts_for_session(session_id)
                if (artifact.get("metadata") or {}).get("stale")
            ],
        }

    @r.get("/{session_id}/artifacts/{artifact_id}/preview")
    def preview_artifact(session_id: str, artifact_id: str):
        _, target = artifact_target(session_id, artifact_id)
        suffix = target.suffix.lower()
        if suffix in TEXT_PREVIEW_TYPES:
            limit = 100_000
            with target.open("r", encoding="utf-8", errors="replace") as stream:
                content = stream.read(limit + 1)
            return {"kind": "text", "content": content[:limit], "truncated": len(content) > limit,
                    "mime_type": TEXT_PREVIEW_TYPES[suffix], "size": target.stat().st_size, "filename": target.name}
        if suffix in IMAGE_PREVIEW_TYPES:
            return {"kind": "image", "content_url": f"/sessions/{session_id}/artifacts/{artifact_id}/content",
                    "mime_type": IMAGE_PREVIEW_TYPES[suffix], "size": target.stat().st_size, "filename": target.name}
        return {"kind": "download", "mime_type": "application/octet-stream", "size": target.stat().st_size, "filename": target.name}

    @r.get("/{session_id}/artifacts/{artifact_id}/content")
    def artifact_content(session_id: str, artifact_id: str):
        _, target = artifact_target(session_id, artifact_id)
        suffix = target.suffix.lower()
        if suffix not in IMAGE_PREVIEW_TYPES:
            raise HTTPException(status_code=415, detail="仅安全的位图产物支持内嵌查看")
        return FileResponse(target, media_type=IMAGE_PREVIEW_TYPES[suffix], headers={"X-Content-Type-Options": "nosniff"})

    @r.get("/{session_id}/artifacts/{artifact_id}/download")
    def download_artifact(session_id: str, artifact_id: str):
        _, target = artifact_target(session_id, artifact_id)
        return FileResponse(target, media_type="application/octet-stream", filename=target.name,
                            headers={"X-Content-Type-Options": "nosniff"})

    @r.get("/{session_id}/requirements")
    def list_requirements(session_id: str):
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return {
            "session_id": session_id,
            "requirements": repo.list_requirements_for_session(session_id),
            "current": repo.get_current_requirement(session_id),
        }

    @r.get("/{session_id}/feedback")
    def list_feedback(session_id: str):
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return {"session_id": session_id, "feedback": repo.list_session_feedback(session_id)}

    @r.post("/{session_id}/feedback")
    def submit_feedback(session_id: str, req: SessionFeedbackRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        try:
            return run_service.submit_session_feedback(
                session_id,
                target_type=req.target_type,
                target_id=req.target_id,
                message=req.message,
                requested_action=req.requested_action,
                created_by=req.created_by,
                reason_type=req.reason_type,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/{session_id}/leader/messages")
    def leader_message(session_id: str, req: SessionFeedbackRequest):
        if run_service is None:
            raise HTTPException(status_code=503, detail="run service is not configured")
        try:
            payload = req.model_dump()
            payload["requested_action"] = "replan"
            if run_service.leader_workflow and run_service.leader_workflow.is_managed(session_id):
                return run_service.leader_workflow.message(session_id, **payload)
            feedback = run_service.submit_session_feedback(session_id, **payload)
            return {**run_service.replan_session(session_id), "impact": feedback["impact"]}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Session 不存在") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/{session_id}/leader/discover")
    def discover_skills(session_id: str):
        if not run_service or not run_service.leader_workflow or not run_service.leader_workflow.is_managed(session_id):
            raise HTTPException(status_code=409, detail="此 Session 未启用真实 Leader 规划")
        return run_service.leader_workflow.discover(session_id)

    @r.post("/{session_id}/replan")
    def request_replan(session_id: str):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        try:
            return run_service.replan_session(session_id)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail="session has no active requirement or cannot be replanned") from exc

    @r.post("/{session_id}/plan-decision")
    def decide_plan(session_id: str, req: PlanDecisionRequest):
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        if run_service is None:
            raise HTTPException(status_code=503, detail="run service is not configured")
        try:
            return run_service.decide_session_plan(session_id, req.approved, req.approver_id, req.reason, req.plan_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

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

    @r.get("/{session_id}/checkpoints")
    def list_checkpoints(session_id: str):
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return {"session_id": session_id, "checkpoints": repo.list_checkpoints(session_id), "rollbacks": repo.list_rollback_events(session_id)}

    @r.post("/{session_id}/checkpoints")
    def create_checkpoint(session_id: str, req: CheckpointRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        return run_service.create_checkpoint(session_id, req.label, req.reason)

    @r.post("/{session_id}/rollback")
    def rollback_session(session_id: str, req: RollbackRequest):
        if run_service is None:
            return {"status": "unavailable", "reason": "run service is not configured"}
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        try:
            return run_service.rollback_session(session_id, req.checkpoint_id, req.reason, req.actor_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown checkpoint: {req.checkpoint_id}") from exc

    return r
