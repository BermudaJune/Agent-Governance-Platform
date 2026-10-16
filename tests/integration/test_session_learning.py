from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from agentgov.app import create_app
from agentgov.memory.cases import SessionCaseService
from agentgov.providers.scripted_model import ModelResponse, ScriptedModelProvider
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


@pytest.fixture
def learning(tmp_path, monkeypatch):
    prompts = []

    def complete(self, prompt, agent_id, tools=None, system_prompt=""):
        prompts.append({"prompt": prompt, "agent": agent_id, "system": system_prompt})
        return ModelResponse("Verified response", 13, 7)

    monkeypatch.setattr(ScriptedModelProvider, "complete", complete)
    database = f"sqlite:///{tmp_path / 'learning.db'}"
    client = TestClient(create_app(database=database, config_path="config/examples/local.scripted.yaml"))
    return client, Repository(database), prompts


def dispatch(client, *, objective="weather story", owner="operator", execute=True):
    response = client.post("/tasks/dispatch", json={
        "title": "Private story assignment", "owner_id": owner, "agent_id": "coordinator",
        "input_summary": objective, "execute_now": execute,
    })
    assert response.status_code == 200, response.text
    return response.json()


def review(client, session_id, **kwargs):
    state = client.get(f"/sessions/{session_id}/review").json()
    return client.post(f"/sessions/{session_id}/review", json={"snapshot_key": state["snapshot_key"], **kwargs})


def test_acceptance_is_explicit_and_atomic_idempotent(learning):
    client, repo, _ = learning
    task = dispatch(client, execute=False)
    session_id = task["session_id"]
    assert review(client, session_id).status_code == 409
    assert not repo.query_all("session_cases")
    client.post(f"/runs/{task['run_id']}/execute")
    assert repo.get_session(session_id)["status"] == "completed"
    assert not repo.query_all("experience_candidates")
    before = client.get(f"/sessions/{session_id}/review").json()
    assert before["can_accept"] and before["current_case"] is None
    payload = dict(snapshot_key=before["snapshot_key"], outcome="accepted", reviewer_id="operator",
                   notes="Meets acceptance criteria", satisfaction=5, reusable_guidance="Weather story: verify source before drafting",
                   share_scope="shared_methods", tags=["weather", "story"], proposal_target="task_strategy")
    service = SessionCaseService(repo)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: service.archive(session_id, **payload), range(2)))
    assert len({result["case"]["id"] for result in results}) == 1
    assert sum(not result["already_archived"] for result in results) == 1
    case = results[0]["case"]
    assert len(repo.query_all("session_cases")) == 1
    assert len(repo.query_all("experience_candidates")) == 1
    candidate = repo.query_all("experience_candidates")[0]
    assert candidate["source_case_id"] == case["id"]
    assert isinstance(candidate["evidence_refs"], list)
    assert case["case_data"]["metrics"]["model_calls"] == 1
    assert case["case_data"]["metrics"]["input_tokens"] == 13
    assert case["case_data"]["metrics"]["output_tokens"] == 7
    assert case["case_data"]["analysis_basis"] == "recorded_facts_only"
    assert len(repo.query_all("run_steps", "WHERE event_type = 'session.review.archived'")) == 1
    state = client.get(f"/sessions/{session_id}/review").json()
    assert state["current_case"]["id"] == case["id"] and not state["can_accept"]
    for status in ("evaluating", "approved"):
        assert client.post(f"/dashboard/evolution/candidates/{candidate['id']}/decision", json={"status": status}).status_code == 409
    assert repo.query_all("experience_candidates")[0]["status"] == "pending"
    response = client.post(f"/dashboard/evolution/candidates/{candidate['id']}/decision", json={"status": "rejected", "reason": "Insufficient evidence"})
    assert response.status_code == 200, response.text
    assert repo.query_all("experience_candidates")[0]["status"] == "rejected"


def test_recall_is_shared_method_only_owner_scoped_and_pinned(learning):
    client, repo, prompts = learning
    source = dispatch(client, objective="SECRET_PRIVATE_OBJECTIVE")
    case = review(client, source["session_id"], reusable_guidance="Weather story: collect weather before writing",
                  share_scope="shared_methods", tags=["weather", "story"]).json()["case"]
    second = dispatch(client, objective="Write a weather story", execute=False)
    recalled = repo.get_session(second["session_id"])["metadata"]["case_recall"]
    assert [item["case_id"] for item in recalled] == [case["id"]]
    assert "SECRET_PRIVATE_OBJECTIVE" not in str(recalled)
    assert "Private story assignment" not in str(recalled)
    assert client.post(f"/memory/cases/{case['id']}/sharing", json={"share_scope": "private"}).status_code == 200
    assert repo.get_session(second["session_id"])["metadata"]["case_recall"] == recalled
    client.post(f"/runs/{second['run_id']}/execute")
    assert case["reusable_guidance"] in prompts[-1]["prompt"]
    assert "untrusted data" in prompts[-1]["prompt"]
    assert "SECRET_PRIVATE_OBJECTIVE" not in prompts[-1]["prompt"]
    assert case["reusable_guidance"] not in prompts[-1]["system"]
    events = repo.list_steps(second["run_id"])
    assert any(event["event_type"] == "session.cases.referenced" for event in events)
    third = dispatch(client, execute=False)
    assert repo.get_session(third["session_id"])["metadata"]["case_recall"] == []
    client.post(f"/memory/cases/{case['id']}/sharing", json={"share_scope": "shared_methods"})
    other_owner = dispatch(client, owner="other", execute=False)
    assert repo.get_session(other_owner["session_id"])["metadata"]["case_recall"] == []
    unrelated = dispatch(client, objective="database migration", execute=False)
    assert repo.get_session(unrelated["session_id"])["metadata"]["case_recall"] == []


def test_new_requirement_invalidates_current_acceptance_preserves_case(learning):
    client, repo, _ = learning
    task = dispatch(client)
    session_id = task["session_id"]
    case = review(client, session_id).json()["case"]
    client.post(f"/sessions/{session_id}/feedback", json={
        "message": "Add a summary", "reason_type": "new_requirement",
    })
    state = client.get(f"/sessions/{session_id}/review").json()
    assert state["current_case"] is None and len(state["cases"]) == 1
    assert not state["can_accept"]
    assert repo.list_session_feedback(session_id)[0]["reason_type"] == "new_requirement"
    stale = client.post(f"/sessions/{session_id}/review", json={"snapshot_key": case["snapshot_key"]})
    assert stale.status_code == 409
    assert repo.query_all("session_cases")[0]["case_data"] == case["case_data"]


def test_pending_approval_and_stale_artifact_block_acceptance(learning):
    client, repo, _ = learning
    task = dispatch(client)
    session_id, run_id = task["session_id"], task["run_id"]
    approval_id = repo.insert_generic("approvals", {
        "run_id": run_id, "status": "pending", "requested_by": "coordinator", "action_summary": {},
        "created_at": now_iso(),
    })
    assert review(client, session_id).status_code == 409
    repo.update_generic("approvals", approval_id, {"status": "approved"})
    repo.insert_generic("artifacts", {
        "session_id": session_id, "run_id": run_id, "created_by_agent_id": "coordinator", "artifact_type": "text",
        "path": "draft.md", "summary": "Old draft", "metadata": {"stale": True}, "created_at": now_iso(),
    })
    assert review(client, session_id).status_code == 409


@pytest.mark.parametrize("outcome", ["failed", "cancelled"])
def test_negative_cases_preserve_outcome_and_need_explicit_sharing(learning, outcome):
    client, repo, _ = learning
    task = dispatch(client, execute=False)
    if outcome == "failed":
        repo.update_run_status(task["run_id"], "failed", error="Provider timeout")
        repo.update_session_status(task["session_id"], "failed")
    else:
        client.post(f"/sessions/{task['session_id']}/cancel", json={})
    assert review(client, task["session_id"]).status_code == 409
    response = review(client, task["session_id"], outcome=outcome, reusable_guidance="weather retries need a limit")
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["outcome"] == outcome and case["share_scope"] == "private"
    assert case["case_data"]["root_cause_status"] == "unconfirmed"
    assert not SessionCaseService(repo).recall("operator", "weather")


def test_retry_can_finish_and_accept_without_erasing_failure(learning):
    client, repo, _ = learning
    task = dispatch(client, execute=False)
    repo.update_run_status(task["run_id"], "failed", error="timeout")
    repo.update_session_status(task["session_id"], "failed")
    old = review(client, task["session_id"], outcome="failed").json()["case"]
    response = client.post(f"/runs/{task['run_id']}/retry", json={"execute_now": True})
    assert response.status_code == 200, response.text
    assert repo.get_session(task["session_id"])["status"] == "completed"
    case = review(client, task["session_id"]).json()["case"]
    assert case["id"] != old["id"]
    assert {run["status"] for run in case["case_data"]["runs"]} == {"failed", "completed"}


@pytest.mark.parametrize("execute_now", [False, True])
def test_leader_entry_and_plan_can_be_accepted_after_execution(learning, execute_now):
    client, repo, _ = learning
    response = client.post("/tasks/dispatch-leader", json={
        "leader_id": "coordinator", "input_summary": "Summarize the findings", "execute_now": execute_now,
    })
    assert response.status_code == 200, response.text
    session_id = response.json()["session_id"]
    assert response.json()["status"] == "awaiting_approval"
    assert not repo.query_all("model_calls")
    assert client.post(f"/sessions/{session_id}/execute-pending").json()["status"] == "awaiting_approval"
    assert review(client, session_id).status_code == 409
    decision = client.post(f"/sessions/{session_id}/plan-decision", json={"approved": True})
    assert decision.status_code == 200, decision.text
    client.post(f"/sessions/{session_id}/execute-pending")
    response = review(client, session_id)
    assert response.status_code == 200, response.text
    case = response.json()["case"]
    assert case["case_data"]["dag"]["nodes"] and case["case_data"]["plans"]
    assert case["case_data"]["decision_refs"]


def test_empty_sharing_is_rejected_and_cases_searchable(learning):
    client, repo, _ = learning
    task = dispatch(client)
    assert review(client, task["session_id"], share_scope="shared_methods").status_code == 422
    case = review(client, task["session_id"], tags=["weather"], notes="good").json()["case"]
    assert client.get("/memory/cases?q=weather").json()["cases"][0]["id"] == case["id"]
    assert not client.get("/memory/cases?owner_id=other").json()["cases"]
    assert client.get("/memory/cases?q=unrelated").json()["cases"] == []
    assert client.get("/sessions/missing/review").status_code == 404
    assert client.get("/memory/cases/missing").status_code == 404
    assert client.post(f"/memory/cases/{case['id']}/sharing", json={"share_scope": "shared_methods"}).status_code == 422
