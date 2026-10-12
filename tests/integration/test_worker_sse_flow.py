from __future__ import annotations

from fastapi.testclient import TestClient

from agentgov.app import create_app


def test_enqueue_worker_matching_snapshot_artifact_and_message_flow(tmp_path):
    db = f"sqlite:///{tmp_path / 'worker.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))

    result = client.post(
        "/tasks/dispatch-ad-hoc-team",
        json={
            "leader": "story_writer",
            "members": ["story_writer", "story_reviewer"],
            "title": "custom writing task",
            "input_summary": "写一首诗到文件，再让另一个 Agent 鉴赏",
            "strategy": "sequential_artifact_review",
            "execute_mode": "enqueue",
        },
    )

    assert result.status_code == 200
    payload = result.json()
    assert payload["execute_mode"] == "enqueue"
    assert payload["matching"]["score"] == 1
    assert payload["team_snapshot"]["session_id"] == payload["session_id"]
    assert len(payload["queue"]) == len(payload["run_ids"])

    processed = client.post("/worker/tick").json()
    assert processed["processed"] == 1
    detail_after_one = client.get(f"/dashboard/sessions/{payload['session_id']}").json()
    assert detail_after_one["session"]["status"] in {"pending", "running"}

    while True:
        processed = client.post("/worker/tick").json()
        if processed["processed"] == 0:
            break

    detail = client.get(f"/dashboard/sessions/{payload['session_id']}").json()
    assert detail["session"]["status"] == "completed"
    assert detail["matching_reports"]
    assert detail["team_snapshot"]["leader_agent_id"] == "story_writer"
    assert len(detail["artifacts"]) >= 2
    assert any(message["message_type"] == "task.assigned" for message in detail["messages"])
    assert any(message["message_type"] == "task.result" for message in detail["messages"])
    assert any(step["event_type"] == "queue.item.created" for step in detail["steps"])
    assert any(step["event_type"] == "queue.item.leased" for step in detail["steps"])
    assert any(step["event_type"] == "queue.item.completed" for step in detail["steps"])


def test_team_match_endpoint_flags_missing_weather(tmp_path):
    db = f"sqlite:///{tmp_path / 'match.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))

    result = client.post(
        "/teams/match",
        json={
            "task_input": "查询天气，写一首诗到文件，再让另一个 Agent 鉴赏",
            "agent_ids": ["story_writer", "story_reviewer"],
            "team_id": "story_team",
        },
    )

    assert result.status_code == 200
    report = result.json()["report"]
    assert "external.weather" in report["missing_capabilities"]
    assert report["score"] < 1
