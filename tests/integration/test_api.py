from __future__ import annotations

from fastapi.testclient import TestClient

from agentgov.app import create_app


def test_api_smoke(tmp_path):
    db = f"sqlite:///{tmp_path / 'api.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    assert client.get("/health").json()["status"] == "ok"
    session = client.post("/sessions", json={"title": "api", "owner_id": "u"}).json()
    run = client.post("/runs", json={"session_id": session["id"], "agent_id": "coordinator", "input_summary": "hello"}).json()
    assert client.get(f"/runs/{run['id']}").json()["run"]["id"] == run["id"]
    assert client.get("/dashboard/overview").json()["runs"] == 1


def test_story_session_is_traceable(tmp_path):
    db = f"sqlite:///{tmp_path / 'story.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    result = client.post("/tasks/demo/story-session", json={})

    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "completed"
    detail = client.get(f"/dashboard/sessions/{payload['session_id']}").json()
    assert detail["session"]["status"] == "completed"
    assert len(detail["runs"]) == 2
    assert {run["agent_id"] for run in detail["runs"]} == {"story_writer", "story_reviewer"}
    assert {ref["path"].split("\\")[-1] for ref in detail["evidence_refs"]} == {"story.md", "review.md"}

    graph = client.get(f"/dashboard/topology/sessions/{payload['session_id']}").json()
    assert any(node["type"] == "session" for node in graph["nodes"])
    assert any(node["type"] == "artifact" for node in graph["nodes"])
    assert any(edge["type"] in {"writes_artifact", "reads_artifact"} for edge in graph["edges"])


def test_team_task_dispatch_and_topology(tmp_path):
    db = f"sqlite:///{tmp_path / 'team.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    result = client.post(
        "/tasks/dispatch-team",
        json={
            "team_id": "governance_review_team",
            "title": "team review",
            "input_summary": "review governance traceability",
            "strategy": "planner_executor_reviewer",
            "execute_now": True,
        },
    )

    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "completed"
    assert len(payload["child_run_ids"]) == 4

    session_graph = client.get(f"/dashboard/topology/sessions/{payload['session_id']}").json()
    assert any(edge["type"] == "delegates_to" for edge in session_graph["edges"])
    assert any(edge["type"] == "task.assigned" for edge in session_graph["edges"])

    team_graph = client.get("/dashboard/topology/teams?team_id=governance_review_team").json()
    assert any(node["id"] == "team:governance_review_team" for node in team_graph["nodes"])
    assert any(edge["type"] == "can_delegate" for edge in team_graph["edges"])


def test_provider_failure_is_a_failed_run_not_http_500(tmp_path, monkeypatch):
    monkeypatch.delenv("XINGWAN_API_KEY", raising=False)
    config = tmp_path / "missing-key.yaml"
    config.write_text(
        """
providers:
  - name: missing-key
    protocol: openai
    base_url: https://example.test/v1
    api_key_env: XINGWAN_API_KEY
    model: test-model
agents:
  - id: coordinator
    name: Coordinator
    provider: missing-key
    model: test-model
""",
        encoding="utf-8",
    )
    db = f"sqlite:///{tmp_path / 'failure.db'}"
    client = TestClient(create_app(database=db, config_path=str(config)))
    result = client.post(
        "/tasks/dispatch",
        json={
            "title": "provider failure",
            "agent_id": "coordinator",
            "input_summary": "this should return a structured failure",
            "execute_now": True,
        },
    )

    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "failed"
    run = client.get(f"/runs/{payload['run_id']}").json()["run"]
    assert run["status"] == "failed"
    assert run["error"]
