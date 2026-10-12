from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.capabilities.requirements import RequirementAnalyzer
from agentgov.config.loader import load_config
from agentgov.runtime.run_service import RunService
from agentgov.storage.repositories import Repository
from agentgov.teams.matching import TeamMatcher
from agentgov.teams.snapshots import TeamSnapshotService


class DispatchTaskRequest(BaseModel):
    title: str = "新任务"
    owner_id: str = "operator"
    agent_id: str
    input_summary: str
    team_id: str | None = None
    execute_now: bool = True
    execute_mode: str | None = None


class DispatchTeamTaskRequest(BaseModel):
    title: str = "多 Agent 协作任务"
    owner_id: str = "operator"
    team_id: str
    input_summary: str
    strategy: str | None = None
    execute_now: bool = True
    execute_mode: str | None = None
    use_llm_matching: bool = False
    force: bool = False


class DispatchAdHocTeamTaskRequest(BaseModel):
    title: str = "临时多 Agent 协作任务"
    owner_id: str = "operator"
    leader: str
    members: list[str]
    input_summary: str
    strategy: str = "leader_worker"
    execute_now: bool = False
    execute_mode: str | None = None
    use_llm_matching: bool = False
    force: bool = False


class StoryDemoRequest(BaseModel):
    owner_id: str = "operator"
    execute_now: bool = True


def _mode(execute_now: bool, execute_mode: str | None) -> str:
    if execute_mode:
        return execute_mode
    return "sync" if execute_now else "manual"


def router(
    run_service: RunService,
    config_path: str = "config/examples/local.scripted.yaml",
    repo: Repository | None = None,
    registry: CapabilityRegistry | None = None,
) -> APIRouter:
    r = APIRouter(prefix="/tasks", tags=["tasks"])
    analyzer = RequirementAnalyzer()
    matcher = TeamMatcher(registry) if registry else None
    snapshots = TeamSnapshotService(repo, registry) if repo and registry else None

    @r.post("/dispatch")
    def dispatch(req: DispatchTaskRequest):
        mode = _mode(req.execute_now, req.execute_mode)
        session = run_service.create_session(
            title=req.title,
            owner_id=req.owner_id,
            root_agent_id=req.agent_id,
            team_id=req.team_id,
        )
        run = run_service.create_run(
            session_id=session.id,
            agent_id=req.agent_id,
            input_summary=req.input_summary,
        )
        if mode == "sync":
            result = run_service.execute(run.id)
        elif mode == "enqueue":
            result = run_service.enqueue_run(run.id)
        else:
            result = None
        return {
            "session_id": session.id,
            "run_id": run.id,
            "agent_id": req.agent_id,
            "executed": mode == "sync",
            "execute_mode": mode,
            "status": result["status"] if isinstance(result, dict) and "status" in result else "created",
            "result": result,
        }

    @r.post("/dispatch-team")
    def dispatch_team(req: DispatchTeamTaskRequest):
        mode = _mode(req.execute_now, req.execute_mode)
        cfg = load_config(config_path)
        team = next((item for item in cfg.teams if item.id == req.team_id), None)
        if team is None:
            raise HTTPException(status_code=404, detail=f"unknown team: {req.team_id}")
        match_payload = _match_or_block(req.input_summary, [team.leader, *team.members], team.id, req.use_llm_matching, req.force)
        if match_payload.get("blocked"):
            return match_payload
        result = run_service.create_team_task(
            title=req.title,
            owner_id=req.owner_id,
            team_id=team.id,
            leader=team.leader,
            members=team.members,
            input_summary=req.input_summary,
            strategy=req.strategy or team.collaboration_strategy,
            execute_now=mode == "sync",
        )
        _attach_matching_and_snapshot(result, match_payload, team.leader, team.members, req.strategy or team.collaboration_strategy)
        if mode == "enqueue":
            result["queue"] = [run_service.enqueue_run(run_id) for run_id in result["run_ids"]]
        result["execute_mode"] = mode
        result["matching"] = match_payload.get("report")
        return result

    @r.post("/dispatch-ad-hoc-team")
    def dispatch_ad_hoc_team(req: DispatchAdHocTeamTaskRequest):
        mode = _mode(req.execute_now, req.execute_mode)
        members = list(dict.fromkeys([req.leader, *req.members]))
        if len(members) < 2:
            raise HTTPException(status_code=400, detail="ad-hoc team requires at least two agents")
        cfg = load_config(config_path)
        known_agents = {agent.id for agent in cfg.agents}
        unknown = [agent_id for agent_id in members if agent_id not in known_agents]
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown agents: {', '.join(unknown)}")
        team_id = f"adhoc:{req.leader}"
        match_payload = _match_or_block(req.input_summary, members, team_id, req.use_llm_matching, req.force)
        if match_payload.get("blocked"):
            return match_payload
        result = run_service.create_team_task(
            title=req.title,
            owner_id=req.owner_id,
            team_id=team_id,
            leader=req.leader,
            members=members,
            input_summary=req.input_summary,
            strategy=req.strategy,
            execute_now=mode == "sync",
        )
        _attach_matching_and_snapshot(result, match_payload, req.leader, members, req.strategy)
        if mode == "enqueue":
            result["queue"] = [run_service.enqueue_run(run_id) for run_id in result["run_ids"]]
        result["execute_mode"] = mode
        result["matching"] = match_payload.get("report")
        return result

    @r.post("/demo/story-session")
    def story_session(req: StoryDemoRequest):
        return run_service.create_story_session(owner_id=req.owner_id, execute_now=req.execute_now)

    def _match_or_block(task_input: str, agent_ids: list[str], team_id: str, use_llm: bool, force: bool) -> dict:
        if matcher is None or repo is None:
            return {"report": None}
        requirement = analyzer.analyze(task_input, use_llm=use_llm)
        report = matcher.match_team(requirement, agent_ids, team_id=team_id, use_llm=use_llm)
        report_id = repo.insert_matching_report(report.model_dump())
        payload = {"requirement": requirement.model_dump(), "report": {**report.model_dump(), "id": report_id}}
        if report.decision == "block" and not force:
            return {"blocked": True, "status": "blocked", **payload}
        return payload

    def _attach_matching_and_snapshot(result: dict, match_payload: dict, leader: str, members: list[str], strategy: str) -> None:
        if repo is None or snapshots is None:
            return
        report = match_payload.get("report") or {}
        report_id = report.get("id")
        if report_id:
            repo.update_generic("team_matching_reports", report_id, {"session_id": result["session_id"]})
        snapshot = snapshots.create_snapshot(
            session_id=result["session_id"],
            leader_agent_id=leader,
            member_agent_ids=members,
            collaboration_strategy=strategy,
            matching_report_id=report_id,
        )
        result["team_snapshot"] = snapshot.model_dump()

    return r
