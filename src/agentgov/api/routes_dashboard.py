from __future__ import annotations

from fastapi import APIRouter

from agentgov.dashboard.audit_query import audit_events
from agentgov.dashboard.service import DashboardService
from agentgov.dashboard.topology import session_graph, team_graph, topology
from agentgov.storage.repositories import Repository


def router(repo: Repository, config_path: str = "config/examples/local.scripted.yaml") -> APIRouter:
    r = APIRouter(prefix="/dashboard", tags=["dashboard"])
    service = DashboardService(repo)

    @r.get("/overview")
    def overview():
        return service.overview()

    @r.get("/runs/{run_id}")
    def run_detail(run_id: str):
        return service.run_detail(run_id)

    @r.get("/sessions/{session_id}")
    def session_detail(session_id: str):
        return service.session_detail(session_id)

    @r.get("/agents/{agent_id}")
    def agent_detail(agent_id: str):
        return service.agent_detail(agent_id)

    @r.get("/topology")
    def get_topology():
        return topology(repo)

    @r.get("/topology/sessions/{session_id}")
    def get_session_topology(session_id: str):
        return session_graph(repo, session_id)

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
