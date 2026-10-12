from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.capabilities.requirements import RequirementAnalyzer
from agentgov.storage.repositories import Repository
from agentgov.teams.matching import TeamMatcher
from agentgov.teams.snapshots import TeamSnapshotService


class MatchTeamRequest(BaseModel):
    task_input: str
    agent_ids: list[str]
    team_id: str | None = None
    use_llm: bool = False


class SaveTemplateRequest(BaseModel):
    name: str
    description: str = ""


def router(repo: Repository, registry: CapabilityRegistry) -> APIRouter:
    r = APIRouter(prefix="/teams", tags=["teams"])
    analyzer = RequirementAnalyzer()
    matcher = TeamMatcher(registry)
    snapshots = TeamSnapshotService(repo, registry)

    @r.post("/match")
    def match_team(req: MatchTeamRequest):
        requirement = analyzer.analyze(req.task_input, use_llm=req.use_llm)
        report = matcher.match_team(requirement, req.agent_ids, team_id=req.team_id, use_llm=req.use_llm)
        return {"requirement": requirement.model_dump(), "report": report.model_dump()}

    @r.get("/templates")
    def list_templates():
        return repo.list_team_templates()

    @r.post("/templates/from-session/{session_id}")
    def save_template_from_session(session_id: str, req: SaveTemplateRequest):
        try:
            return snapshots.save_template_from_session(session_id, req.name, req.description).model_dump()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @r.get("/history")
    def history():
        return {
            "templates": repo.list_team_templates(),
            "snapshots": repo.query_all("session_team_snapshots", "ORDER BY created_at DESC"),
            "matching_reports": repo.query_all("team_matching_reports", "ORDER BY created_at DESC LIMIT 100"),
        }

    return r
