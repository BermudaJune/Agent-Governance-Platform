from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from agentgov.api import routes_agents, routes_approvals, routes_config, routes_dashboard, routes_events, routes_governance, routes_knowledge, routes_runs, routes_sessions, routes_skills, routes_tasks, routes_teams, routes_tools
from agentgov.api import routes_memory
from agentgov.budget.service import BudgetService
from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.config.loader import load_config
from agentgov.event_stream.stream import EventStream
from agentgov.gateway.model import ModelGateway
from agentgov.gateway.skill import SkillGateway
from agentgov.gateway.tool import ToolGateway
from agentgov.gateway.tool_registry import ToolRegistry
from agentgov.providers.local_repo_tools import LocalRepoTools
from agentgov.providers.openai_compatible import OpenAICompatibleProvider
from agentgov.providers.scripted_model import ScriptedModelProvider
from agentgov.planning.planner import RuleBasedSessionPlanner
from agentgov.runtime.agent_loop import AgentLoop
from agentgov.runtime.run_service import RunService
from agentgov.runtime.leader_workflow import LeaderWorkflowService
from agentgov.sandbox.local_readonly import LocalReadOnlySandboxRuntime
from agentgov.sandbox.service import SandboxService
from agentgov.scheduler.queue import RunQueue
from agentgov.scheduler.worker import RunWorker
from agentgov.storage.db import init_db
from agentgov.storage.repositories import Repository


class Utf8JSONResponse(JSONResponse):
    media_type = "application/json; charset=utf-8"


def create_app(
    database: str = "sqlite:///./data/agentgov.db",
    config_path: str = "config/examples/local.scripted.yaml",
) -> FastAPI:
    init_db(database)
    repo = Repository(database)
    cfg = load_config(config_path)
    capability_registry = CapabilityRegistry(cfg)
    provider_cfg = cfg.providers[0]
    model_cfg = provider_cfg.models[0] if provider_cfg.models else None
    model_name = model_cfg.name if model_cfg else "default"
    provider = (
        OpenAICompatibleProvider(provider_cfg.base_url or "", provider_cfg.api_key_env or "", model_name, api_key=provider_cfg.api_key)
        if provider_cfg.protocol.value == "openai"
        else ScriptedModelProvider(provider_cfg.script or "default")
    )
    events = EventStream(repo)
    budget = BudgetService(repo)
    sandbox_cfg = cfg.sandboxes[0] if cfg.sandboxes else None
    sandbox_runtime = LocalReadOnlySandboxRuntime(
        root=sandbox_cfg.root if sandbox_cfg else ".",
        allowed_commands=sandbox_cfg.allowed_commands if sandbox_cfg else ["rg", "python"],
        timeout_seconds=sandbox_cfg.timeout_seconds if sandbox_cfg else 20,
    )
    sandbox = SandboxService(repo, events, sandbox_runtime)
    repo_tools = LocalRepoTools(".")
    tool_registry = ToolRegistry.from_config(cfg, repo_tools, sandbox)
    model_gateway = ModelGateway(
        repo,
        events,
        budget,
        provider,
        provider_cfg.name,
        model_name,
        input_price_per_1k=model_cfg.input_price_per_1k if model_cfg else 0.0,
        output_price_per_1k=model_cfg.output_price_per_1k if model_cfg else 0.0,
        system_prompts_by_agent={agent.id: agent.system_prompt for agent in cfg.agents},
    )
    tool_gateway = ToolGateway(
        repo,
        events,
        tool_registry,
        allowed_tools_by_agent=lambda: {agent.id: agent.tools for agent in load_config(config_path).agents},
    )
    skill_gateway = SkillGateway(repo, events, capability_registry, config_path=config_path)
    run_queue = RunQueue(repo)
    run_service = RunService(repo, events, AgentLoop(model_gateway, tool_gateway, skill_gateway), run_queue, RuleBasedSessionPlanner(cfg))
    if provider_cfg.protocol.value == "openai":
        run_service.leader_workflow = LeaderWorkflowService(run_service, config_path)
    worker = RunWorker(run_service, run_queue, events)
    app = FastAPI(title="Agent Governance Platform", version="0.1.0", default_response_class=Utf8JSONResponse)

    @app.get("/")
    def root() -> dict[str, object]:
        return {
            "name": "Agent Governance Platform",
            "status": "ok",
            "docs": "/docs",
            "health": "/health",
            "console": "http://127.0.0.1:5173",
            "endpoints": ["/config", "/agents", "/tasks/dispatch", "/sessions", "/runs", "/dashboard/overview", "/dashboard/audit"],
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(routes_agents.router(config_path))
    app.include_router(routes_config.router(config_path))
    app.include_router(routes_sessions.router(repo, run_service, config_path, workspace_root=repo_tools.root))
    app.include_router(routes_governance.router(repo, config_path, run_service))
    app.include_router(routes_knowledge.router(repo))
    app.include_router(routes_memory.router(repo))
    app.include_router(routes_tasks.router(run_service, config_path, repo, capability_registry))
    app.include_router(routes_runs.router(repo, run_service))
    app.include_router(routes_approvals.router(repo, run_service, config_path))
    app.include_router(routes_dashboard.router(repo, config_path))
    app.include_router(routes_teams.router(repo, capability_registry))
    app.include_router(routes_tools.router(config_path, tool_registry))
    app.include_router(routes_skills.router(config_path))
    app.include_router(routes_events.router(repo))

    @app.post("/worker/tick")
    def worker_tick() -> dict[str, int]:
        return {"processed": worker.tick()}

    return app
