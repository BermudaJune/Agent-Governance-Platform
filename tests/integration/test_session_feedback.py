from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentgov.app import create_app
from agentgov.event_stream.stream import EventStream
from agentgov.planning.models import TaskNodeSpec
from agentgov.planning.service import PlanningService
from agentgov.runtime.agent_loop import AgentLoop
from agentgov.storage.models import RunRecord
from agentgov.storage.repositories import Repository


@pytest.fixture
def feedback_session(tmp_path, monkeypatch):
    prompts = {}

    def run_once(self, run_id, session_id, agent_id, prompt):
        prompts[run_id] = prompt
        return {"status": "completed", "response": f"Evidence from {agent_id}"}

    monkeypatch.setattr(AgentLoop, "run_once", run_once)
    database = f"sqlite:///{tmp_path / 'feedback.db'}"
    client = TestClient(create_app(database=database, config_path="config/examples/local.scripted.yaml"))
    repo = Repository(database)
    session_id = client.post("/sessions", json={"title": "Feedback test", "root_agent_id": "coordinator"}).json()["id"]
    requirement = repo.create_requirement_version(session_id, "Review the evidence")
    specs = [
        TaskNodeSpec(node_key="source", assigned_agent_id="coordinator", title="Source", instruction="Collect evidence"),
        TaskNodeSpec(node_key="draft", assigned_agent_id="coordinator", title="Draft", instruction="Write a draft", depends_on=["source"]),
        TaskNodeSpec(node_key="review", assigned_agent_id="coordinator", title="Review", instruction="Review draft", depends_on=["draft"]),
        TaskNodeSpec(node_key="parallel", assigned_agent_id="coordinator", title="Parallel", instruction="Independent task"),
    ]
    run_ids = {
        spec.node_key: repo.create_run(RunRecord(session_id=session_id, agent_id=spec.assigned_agent_id, input_summary=spec.instruction)).id
        for spec in specs
    }
    PlanningService(repo, EventStream(repo)).create_plan(
        session_id=session_id, objective="Review the evidence", strategy="leader_worker",
        planner_agent_id="coordinator", nodes=specs, run_ids_by_node_key=run_ids,
        requirement_id=requirement["id"], approval_status="approved",
    )
    nodes = {node["node_key"]: node for node in repo.list_task_nodes_for_session(session_id)}
    return client, repo, session_id, nodes, prompts


def test_feedback_replan_reuses_evidence_and_audits_decision(feedback_session):
    client, repo, session_id, nodes, prompts = feedback_session
    prefix = f"/sessions/{session_id}"
    source_run = nodes["source"]["run_id"]
    assert client.post(f"/runs/{source_run}/execute").json()["status"] == "completed"

    feedback = client.post(f"{prefix}/feedback", json={
        "target_type": "action", "target_id": nodes["draft"]["id"], "message": "Keep the source, revise the ending",
    })
    assert feedback.status_code == 200
    assert set(feedback.json()["impact"]["affected_node_keys"]) == {"draft", "review"}
    dashboard = client.get(f"/dashboard/sessions/{session_id}").json()
    assert dashboard["replan_required"] is True
    assert dashboard["current_requirement"]["version"] == 2
    assert len(dashboard["feedback"]) == 1
    assert client.post(f"{prefix}/execute-pending").json()["executed"] == 0
    assert client.post(f"/runs/{nodes['draft']['run_id']}/execute").json()["status"] == "blocked"

    replan = client.post(f"{prefix}/replan").json()
    assert replan["status"] == "awaiting_approval"
    plan = repo.get_plan_for_session(session_id)
    replacements = repo.list_task_nodes_for_plan(plan["id"])
    assert len(replacements) == 2
    assert client.post(f"{prefix}/execute-pending").json()["executed"] == 0
    assert client.post(f"/runs/{replacements[0]['run_id']}/execute").json()["status"] == "blocked"
    # Queueing must not replace the pending approval with an active status.
    PlanningService(repo, EventStream(repo)).enqueue_ready_nodes_for_session(session_id)
    assert repo.get_plan_for_session(session_id)["status"] == "awaiting_approval"

    assert client.post(f"{prefix}/plan-decision", json={"approved": True, "reason": "Looks good"}).json()["status"] == "approved"
    execution = client.post(f"{prefix}/execute-pending").json()
    assert execution["executed"] == 3  # Two replacement nodes and untouched parallel work.
    assert repo.get_session(session_id)["status"] == "completed"
    assert len(prompts) == 4
    new_draft = next(node for node in replacements if node["title"] == "重规划：Draft")
    assert "Evidence from coordinator" in prompts[new_draft["run_id"]]
    assert "Keep the source, revise the ending" in prompts[new_draft["run_id"]]
    assert repo.get_task_node_for_run(nodes["draft"]["run_id"])["status"] == "superseded"
    events = client.get(f"/dashboard/sessions/{session_id}").json()["steps"]
    assert any(event["event_type"] == "session.plan.decided" and event["payload"]["approved"] for event in events)

    second_feedback = client.post(f"{prefix}/feedback", json={"message": "Make it shorter"}).json()
    assert len(second_feedback["impact"]["affected_node_ids"]) == 4
    assert len(second_feedback["requirement"]["contract"]["corrections"]) == 2


def test_rejected_plan_can_be_replanned_without_replaying_old_nodes(feedback_session):
    client, repo, session_id, nodes, prompts = feedback_session
    prefix = f"/sessions/{session_id}"
    client.post(f"{prefix}/feedback", json={"message": "Change the plan"})
    client.post(f"{prefix}/replan")
    plan = repo.get_plan_for_session(session_id)
    assert client.post(f"{prefix}/plan-decision", json={"approved": False}).json()["status"] == "rejected"
    assert client.post(f"{prefix}/execute-pending").json()["executed"] == 0
    result = client.post(f"{prefix}/replan").json()
    assert result["status"] == "awaiting_approval"
    replacement_plan = repo.get_plan_for_session(session_id)
    assert replacement_plan["version"] == 3
    assert replacement_plan["parent_plan_id"] == plan["id"]
    assert len(repo.list_task_nodes_for_plan(replacement_plan["id"])) == 4
    assert client.post(f"{prefix}/plan-decision", json={"approved": True}).status_code == 200
    assert client.post(f"{prefix}/execute-pending").json()["executed"] == 4
    assert repo.get_session(session_id)["status"] == "completed"
    assert len(prompts) == 4


def test_feedback_rejects_empty_and_foreign_targets_without_changes(feedback_session):
    client, repo, session_id, nodes, prompts = feedback_session
    for payload in [
        {"message": "   "},
        {"message": "Change it", "target_type": "action"},
        {"message": "Change it", "target_type": "action", "target_id": "other-session-node"},
        {"message": "Change it", "target_type": "unknown"},
    ]:
        assert client.post(f"/sessions/{session_id}/feedback", json=payload).status_code == 422
    assert len(repo.list_requirements_for_session(session_id)) == 1
    assert repo.list_session_feedback(session_id) == []
    assert prompts == {}
