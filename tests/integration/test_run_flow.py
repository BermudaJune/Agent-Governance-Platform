from __future__ import annotations

from agentgov.budget.service import BudgetService
from agentgov.event_stream.stream import EventStream
from agentgov.gateway.model import ModelGateway
from agentgov.gateway.tool import ToolGateway
from agentgov.providers.local_repo_tools import LocalRepoTools
from agentgov.providers.scripted_model import ScriptedModelProvider
from agentgov.runtime.agent_loop import AgentLoop
from agentgov.runtime.run_service import RunService
from agentgov.storage.db import init_db
from agentgov.storage.repositories import Repository


def test_scripted_run_flow(tmp_path):
    db = f"sqlite:///{tmp_path / 'run.db'}"
    init_db(db)
    repo = Repository(db)
    events = EventStream(repo)
    budget = BudgetService(repo)
    model = ModelGateway(repo, events, budget, ScriptedModelProvider(), "scripted", "scripted-model")
    tools = ToolGateway(repo, events, LocalRepoTools("."))
    service = RunService(repo, events, AgentLoop(model, tools))

    session = service.create_session("test", "u", root_agent_id="evidence")
    run = service.create_run(session.id, "evidence", "find audit")
    result = service.execute(run.id)

    assert "Evidence collected" in result["response"]
    detail = repo.get_run(run.id)
    assert detail["status"] == "completed"
    events = repo.list_steps(run.id)
    assert any(e["event_type"] == "model.call.finished" for e in events)
    assert any(e["event_type"] == "tool.call.finished" for e in events)
    assert repo.query_all("model_calls", "WHERE run_id = ?", (run.id,))
    assert repo.query_all("tool_calls", "WHERE run_id = ?", (run.id,))
