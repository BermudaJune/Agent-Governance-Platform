from __future__ import annotations

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.config.loader import load_config
from agentgov.event_stream.stream import EventStream
from agentgov.gateway.skill import SkillGateway
from agentgov.gateway.tool import ToolGateway
from agentgov.providers.local_repo_tools import LocalRepoTools
from agentgov.storage.db import init_db
from agentgov.storage.models import RunRecord, SessionRecord
from agentgov.storage.repositories import Repository


def test_skill_gateway_denies_unauthorized_skill_and_logs_policy(tmp_path):
    db = f"sqlite:///{tmp_path / 'skill.db'}"
    init_db(db)
    repo = Repository(db)
    events = EventStream(repo)
    registry = CapabilityRegistry(load_config("config/examples/local.scripted.yaml"))
    gateway = SkillGateway(repo, events, registry)
    session = repo.create_session(SessionRecord(title="skill", owner_id="test"))
    run = repo.create_run(RunRecord(session_id=session.id, agent_id="story_writer", input_summary="load skill"))

    denied = gateway.load_skill(run.id, session.id, "story_writer", "repo.research")
    allowed = gateway.load_skill(run.id, session.id, "story_writer", "writing.basic")

    assert denied["status"] == "denied"
    assert allowed["status"] == "completed"
    assert repo.query_all("policy_decisions", "WHERE run_id = ?", (run.id,))[0]["decision"] == "deny"
    assert any(step["event_type"] == "skill.load.denied" for step in repo.list_steps(run.id))


def test_tool_gateway_records_denial_and_file_artifact(tmp_path):
    db = f"sqlite:///{tmp_path / 'tool.db'}"
    init_db(db)
    repo = Repository(db)
    events = EventStream(repo)
    tool_gateway = ToolGateway(
        repo,
        events,
        LocalRepoTools(str(tmp_path)),
        allowed_tools_by_agent={"writer": ["file_write"]},
    )
    session = repo.create_session(SessionRecord(title="tool", owner_id="test"))
    run = repo.create_run(RunRecord(session_id=session.id, agent_id="writer", input_summary="write file"))

    denied = tool_gateway.call(run.id, session.id, "writer", "repo_read", {"path": "README.md"})
    written = tool_gateway.call(run.id, session.id, "writer", "file_write", {"path": "out.md", "content": "hello"})

    assert denied["status"] == "denied"
    assert written["status"] == "completed"
    assert repo.query_all("policy_decisions", "WHERE run_id = ?", (run.id,))[0]["decision"] == "deny"
    artifacts = repo.list_artifacts_for_session(session.id)
    assert len(artifacts) == 1
    assert artifacts[0]["created_by_agent_id"] == "writer"
    assert artifacts[0]["metadata"]["tool"] == "file_write"
