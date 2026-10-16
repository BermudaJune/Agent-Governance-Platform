from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from agentgov.app import create_app
from agentgov.providers.openai_compatible import OpenAICompatibleProvider
from agentgov.providers.scripted_model import ModelResponse
from agentgov.storage.repositories import Repository


def node(key, instruction=None, **changes):
    return {"node_key": key, "assigned_agent_id": "coordinator", "title": key,
            "instruction": instruction or key, **changes}


def proposal(nodes, **changes):
    return {"understanding": "Understand the user's actual objective", "reply": "Plan ready for review",
            "nodes": nodes, "acceptance": ["Deliver verifiable results"], **changes}


@pytest.fixture
def leader(tmp_path, monkeypatch):
    config = tmp_path / "leader.yaml"
    config.write_text("""
providers:
  - name: real
    protocol: openai
    base_url: https://example.test/v1
    api_key_env: TEST_LEADER_KEY
    model: test
tools:
  - id: file_write
    name: Reviewed file write
    executor: file_write
    category: write
    requires_approval: true
agents:
  - id: coordinator
    name: Leader
    provider: real
    model: test
    tools: [file_write, file_read]
  - id: researcher
    name: Researcher
    provider: real
    model: test
""", encoding="utf-8")
    responses = []
    prompts = []

    def complete(self, prompt, agent_id, **kwargs):
        prompts.append(prompt)
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, ModelResponse):
            return item
        return ModelResponse(json.dumps(item), 10, 10)

    monkeypatch.setattr(OpenAICompatibleProvider, "complete", complete)
    monkeypatch.setattr("agentgov.runtime.leader_workflow.search_github_skill_repositories",
                        lambda query, limit=4: [{"repository": "example/skills", "url": "https://github.com/example/skills"}])
    database = f"sqlite:///{tmp_path / 'leader.db'}"
    return TestClient(create_app(database=database, config_path=str(config))), Repository(database), responses, prompts


def dispatch(client):
    result = client.post("/tasks/dispatch-leader", json={"leader_id": "coordinator", "input_summary": "Create a useful result"})
    assert result.status_code == 200, result.text
    return result.json()


def approve(client, repo, sid):
    return client.post(f"/sessions/{sid}/plan-decision", json={"approved": True, "plan_id": repo.get_plan_for_session(sid)["id"]})


def test_config_reports_environment_key_and_effective_model_without_exposing_secret(leader, monkeypatch):
    client, _, _, _ = leader
    monkeypatch.setenv("TEST_LEADER_KEY", "test-secret")
    provider = client.get("/config").json()["config"]["providers"][0]
    assert provider["api_key"] is None
    assert provider["api_key_configured"] is True
    assert provider["effective_model"] == "test"


def test_correction_replaces_graph_preserves_completed_branch_and_expires_old_approval(leader):
    client, repo, responses, prompts = leader
    responses.append(proposal([node("source"), node("draft", depends_on=["source"])]))
    sid = dispatch(client)["session_id"]
    old_plan = repo.get_plan_for_session(sid)
    assert approve(client, repo, sid).status_code == 200
    source = next(n for n in repo.list_task_nodes_for_session(sid) if n["node_key"] == "source")
    old_draft = next(n for n in repo.list_task_nodes_for_session(sid) if n["node_key"] == "draft")
    responses.append(ModelResponse("Verified source", 10, 10))
    assert client.post(f"/runs/{source['run_id']}/execute").json()["status"] == "completed"
    responses.append(proposal([node("source"), node("rewrite", "New ending", depends_on=["source"]),
                               node("review", depends_on=["rewrite"])], preserve_node_keys=["source"]))
    correction = client.post(f"/sessions/{sid}/leader/messages", json={"message": "Keep evidence, change ending and add review",
        "target_type": "action", "target_id": next(n["id"] for n in repo.list_task_nodes_for_session(sid) if n["node_key"] == "draft")})
    assert correction.status_code == 200, correction.text
    diff = correction.json()["leader"]["diff"]
    assert diff["preserved"] == ["source"]
    assert set(diff["added"]) == {"rewrite", "review"}
    assert diff["removed"] == ["draft"]
    assert "Keep evidence" in prompts[-1]
    assert client.post(f"/sessions/{sid}/plan-decision", json={"approved": True, "plan_id": old_plan["id"]}).status_code == 409
    assert approve(client, repo, sid).status_code == 200
    responses.extend([ModelResponse("New ending", 10, 10), ModelResponse("Reviewed", 10, 10)])
    execution = client.post(f"/sessions/{sid}/execute-pending").json()
    assert execution["executed"] == 2
    assert repo.get_session(sid)["status"] == "completed"
    assert repo.get_run(source["run_id"])["output_summary"] == "Verified source"
    assert any(m["message_type"] == "leader.user" for m in repo.query_all("agent_messages", "WHERE session_id = ?", (sid,)))
    current_graph = client.get(f"/dashboard/topology/sessions/{sid}?current_only=true").json()
    assert f"run:{old_draft['run_id']}" not in {item["id"] for item in current_graph["nodes"]}
    current_nodes = {node["node_key"]: node for node in repo.list_task_nodes_for_session(sid) if node["status"] != "superseded"}
    assignment_edges = [edge for edge in current_graph["edges"] if edge["type"] == "leader.assignment"]
    assert {edge["target"] for edge in assignment_edges} == {
        f"run:{current_nodes['rewrite']['run_id']}",
        f"run:{current_nodes['review']['run_id']}",
    }
    assert all(edge["source"] != edge["target"] for edge in assignment_edges)
    actions = client.get(f"/dashboard/sessions/{sid}/available-actions").json()["actions"]
    execute_pending = next(item for item in actions if item["id"] == "execute-pending")
    assert execute_pending["enabled"] is False
    assert execute_pending["disabled_reason"] == "没有待处理 Run"


def test_provider_failure_preserves_task_and_retry(leader):
    client, repo, responses, _ = leader
    responses.append(RuntimeError("provider unavailable"))
    result = dispatch(client)
    sid = result["session_id"]
    assert result["status"] == "planning_failed"
    assert repo.get_current_requirement(sid)["objective"] == "Create a useful result"
    responses.append(proposal([node("write")]))
    result = client.post(f"/sessions/{sid}/replan").json()
    assert result["status"] == "awaiting_approval"
    assert len(repo.list_task_nodes_for_session(sid)) == 1


def test_replan_does_not_preserve_completed_node_when_promised_file_is_missing(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("write", output_contract={"files": ["delivery.md"]})]))
    sid = dispatch(client)["session_id"]
    assert approve(client, repo, sid).status_code == 200
    old = repo.list_task_nodes_for_session(sid)[0]
    repo.update_run_status(old["run_id"], "completed", output_summary="claimed delivery")
    repo.update_generic("task_nodes", old["id"], {"status": "completed"})
    responses.append(proposal([node("write", output_contract={"files": ["delivery.md"]})], preserve_node_keys=["write"]))

    result = client.post(f"/sessions/{sid}/leader/messages", json={"message": "Keep the finished delivery"})

    assert result.status_code == 200, result.text
    assert result.json()["leader"]["diff"]["preserved"] == []
    assert result.json()["leader"]["diff"]["revised"] == ["write"]


def test_invalid_cycle_has_bounded_repair_then_visible_failure(leader):
    client, repo, responses, prompts = leader
    bad = proposal([node("a", depends_on=["b"]), node("b", depends_on=["a"])])
    responses.extend([bad, bad])
    result = dispatch(client)
    assert result["status"] == "planning_failed"
    assert len(prompts) == 2
    assert repo.list_task_nodes_for_session(result["session_id"]) == []


def test_gap_search_does_not_pretend_runtime_is_installed(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("draw", required_tools=["uninstalled_image_runtime"])],
                              capability_gaps=[{"capability": "image", "reason": "No image provider", "search_query": "image skills"}]))
    result = dispatch(client)
    sid = result["session_id"]
    assert result["status"] == "capability_gap"
    assert result["leader"]["discovery"]
    assert approve(client, repo, sid).status_code == 409
    blocked = client.post(f"/sessions/{sid}/execute-pending").json()
    assert blocked["executed"] == 0
    assert blocked["status"] == "blocked"


@pytest.mark.parametrize("search_fails", [False, True])
def test_gap_routes_remain_available_when_bounded_search_cannot_help(leader, monkeypatch, search_fails):
    client, repo, responses, prompts = leader
    queries = []

    def search(query, limit):
        queries.append(query)
        if search_fails:
            raise RuntimeError("GitHub unavailable")
        return []

    monkeypatch.setattr("agentgov.runtime.leader_workflow.search_github_skill_repositories", search)
    alternative = {"title": "Deliver a storyboard instead", "proposal": "Write a storyboard without generating images",
                   "tradeoff": "No actual image files will be delivered", "prerequisites": ["User accepts changed delivery"]}
    responses.append(proposal([], capability_gaps=[
        {"capability": "illustrations", "reason": "No image runtime", "alternatives": [alternative]},
        {"capability": "weather", "reason": "No weather service"},
        {"capability": "slides", "reason": "No slide renderer"},
    ]))
    result = dispatch(client)
    sid = result["session_id"]
    old_plan = repo.get_plan_for_session(sid)
    assert result["status"] == "capability_gap"
    assert len(queries) == 2
    assert repo.get_session(sid)["status"] == "blocked"
    assert "illustrations" in repo.get_session(sid)["context_summary"]
    assert [d["status"] for d in result["leader"]["discovery"]] == [
        "failed" if search_fails else "no_results", "failed" if search_fails else "no_results", "not_searched"]
    assert result["leader"]["unresolved_gaps"][0]["alternatives"] == [alternative]
    assert result["leader"]["unresolved_gaps"][1]["alternatives"][0]["prerequisites"]
    assert approve(client, repo, sid).status_code == 409
    assert not repo.list_delegation_requests(sid)

    message = "Use the storyboard alternative. No actual image files will be delivered."
    responses.append(proposal([node("storyboard")]))
    revised = client.post(f"/sessions/{sid}/leader/messages", json={"message": message, "reason_type": "preference"})
    assert revised.status_code == 200, revised.text
    assert message in prompts[-1]
    assert revised.json()["status"] == "awaiting_approval"
    assert repo.get_plan_for_session(sid)["approval_status"] == "required"
    assert all(r["status"] != "running" for r in repo.list_runs_for_session(sid))
    assert repo.list_session_feedback(sid)[-1]["message"] == message
    assert client.post(f"/sessions/{sid}/plan-decision", json={"approved": True, "plan_id": old_plan["id"]}).status_code == 409


def test_alternative_choice_is_preserved_if_replanning_model_fails(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([], capability_gaps=[{"capability": "weather", "reason": "No live weather source"}]))
    sid = dispatch(client)["session_id"]
    responses.append(RuntimeError("provider has no access"))
    message = "I will provide weather data. Ask me for the city and timestamp before proceeding."
    result = client.post(f"/sessions/{sid}/leader/messages", json={"message": message}).json()
    assert result["status"] == "planning_failed"
    assert message in json.dumps(repo.get_current_requirement(sid))
    assert repo.list_session_feedback(sid)[-1]["message"] == message
    assert not repo.list_delegation_requests(sid)
    assert client.post(f"/sessions/{sid}/execute-pending").json()["executed"] == 0


def test_expansion_is_shared_idempotent_and_does_not_start_task(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("research", assigned_agent_id="researcher")]))
    sid = dispatch(client)["session_id"]
    request = repo.list_delegation_requests(sid)[0]
    assert request["status"] == "pending"
    first = client.post(f"/approvals/{request['approval_id']}/decide", json={"approved": True})
    assert first.status_code == 200, first.text
    second = client.post(f"/delegations/{request['id']}/decide", json={"approved": True})
    assert second.status_code == 200
    assert second.json()["already_decided"]
    assert client.post(f"/delegations/{request['id']}/decide", json={"approved": False}).status_code == 409
    assert repo.get_plan_for_session(sid)["status"] == "awaiting_approval"
    assert not any(r["status"] == "running" for r in repo.list_runs_for_session(sid))
    assert client.post("/delegations/missing/decide", json={"approved": True}).status_code == 404


def test_missing_promised_file_fails_instead_of_claiming_delivery(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("write", output_contract={"files": ["delivery.md"]})]))
    sid = dispatch(client)["session_id"]
    assert approve(client, repo, sid).status_code == 200
    responses.append(ModelResponse("I have created the file", 10, 10))
    result = client.post(f"/sessions/{sid}/execute-pending").json()
    assert result["status"] == "failed"
    run = next(r for r in repo.list_runs_for_session(sid) if r["run_type"] != "leader_planning")
    assert "delivery.md" in run["error"]


def test_tool_batch_stops_at_approval_and_each_action_needs_its_own_consent(leader):
    client, repo, responses, prompts = leader
    responses.append(proposal([node("write", required_tools=["file_write"],
                                    output_contract={"files": ["first.md", "second.md"]})]))
    sid = dispatch(client)["session_id"]
    assert approve(client, repo, sid).status_code == 200
    first = {"tool": "file_write", "path": "first.md", "content": "first result"}
    second = {"tool": "file_write", "path": "second.md", "content": "second result"}
    responses.append(ModelResponse("", 10, 10, tool_intent={"calls": [first, second]}))
    client.post(f"/sessions/{sid}/execute-pending")
    run = next(r for r in repo.list_runs_for_session(sid) if r["run_type"] != "leader_planning")
    calls = repo.query_all("tool_calls", "WHERE run_id = ? ORDER BY rowid", (run["id"],))
    assert len(calls) == 1
    assert not repo.list_artifacts_for_session(sid)
    responses.append(ModelResponse("", 10, 10, tool_intent={"calls": [first, second]}))
    result = client.post(f"/approvals/{calls[0]['approval_id']}/decide", json={"approved": True})
    assert result.status_code == 200, result.text
    assert len(repo.list_artifacts_for_session(sid)) == 1
    calls = repo.query_all("tool_calls", "WHERE run_id = ? ORDER BY rowid", (run["id"],))
    assert [c["status"] for c in calls] == ["awaiting_approval", "completed", "awaiting_approval"]
    assert calls[-1]["args_summary"]["path"] == "second.md"
    responses.extend([ModelResponse("", 10, 10, tool_intent=second), ModelResponse("Both files saved", 10, 10)])
    result = client.post(f"/approvals/{calls[-1]['approval_id']}/decide", json={"approved": True})
    assert result.status_code == 200, result.text
    assert repo.get_run(run["id"])["status"] == "completed"
    assert len(repo.list_artifacts_for_session(sid)) == 2
    assert "first.md" in prompts[-1] and "completed" in prompts[-1]
    consumed = repo.query_all("policy_decisions", "WHERE run_id = ? AND policy_id = 'approved_action'", (run["id"],))
    assert len({d["metadata"]["approval_id"] for d in consumed}) == 2


def test_pending_expansion_expires_when_user_changes_plan(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("research", assigned_agent_id="researcher")]))
    sid = dispatch(client)["session_id"]
    old = repo.list_delegation_requests(sid)[0]
    responses.append(proposal([node("write")]))
    result = client.post(f"/sessions/{sid}/leader/messages", json={"message": "Only write, no research"})
    assert result.status_code == 200, result.text
    assert client.post(f"/delegations/{old['id']}/decide", json={"approved": True}).status_code == 409
    assert client.post(f"/approvals/{old['approval_id']}/decide", json={"approved": True}).status_code == 409


def test_clarification_blocks_plan_until_answered_and_plan_decision_is_idempotent(leader):
    client, repo, responses, prompts = leader
    responses.append(proposal([], questions=["Which city?"]))
    result = dispatch(client)
    sid = result["session_id"]
    assert result["status"] == "needs_clarification"
    assert approve(client, repo, sid).status_code == 409
    responses.append(proposal([node("write")]))
    result = client.post(f"/sessions/{sid}/leader/messages", json={"message": "Use Shanghai"})
    assert result.status_code == 200, result.text
    assert "Shanghai" in prompts[-1]
    assert approve(client, repo, sid).status_code == 200
    assert approve(client, repo, sid).json()["already_decided"]
    assert client.post(f"/sessions/{sid}/plan-decision", json={"approved": False}).status_code == 409


def test_preserving_all_completed_work_can_be_accepted_without_reexecution(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("write")]))
    sid = dispatch(client)["session_id"]
    assert approve(client, repo, sid).status_code == 200
    responses.append(ModelResponse("Useful result", 10, 10))
    client.post(f"/sessions/{sid}/execute-pending")
    responses.append(proposal([node("write")], preserve_node_keys=["write"]))
    assert client.post(f"/sessions/{sid}/leader/messages", json={"message": "Keep this result unchanged"}).status_code == 200
    assert approve(client, repo, sid).status_code == 200
    assert client.post(f"/sessions/{sid}/execute-pending").json()["executed"] == 0
    assert client.get(f"/sessions/{sid}/review").json()["can_accept"]


def test_unresolved_tool_failure_survives_approval_resume(leader):
    client, repo, responses, _ = leader
    responses.append(proposal([node("read_then_write")]))
    sid = dispatch(client)["session_id"]
    assert approve(client, repo, sid).status_code == 200
    responses.append(ModelResponse("", 10, 10, tool_intent={"calls": [
        {"tool": "file_read", "path": "does-not-exist.md"},
        {"tool": "file_write", "path": "result.md", "content": "partial"}]}))
    client.post(f"/sessions/{sid}/execute-pending")
    run = next(r for r in repo.list_runs_for_session(sid) if r["run_type"] != "leader_planning")
    pending = repo.query_all("approvals", "WHERE run_id = ? AND status = 'pending'", (run["id"],))[0]
    responses.append(ModelResponse("Everything is complete", 10, 10))
    assert client.post(f"/approvals/{pending['id']}/decide", json={"approved": True}).status_code == 200
    assert repo.get_run(run["id"])["status"] == "failed"
    assert "file_read" in repo.get_run(run["id"])["error"]
