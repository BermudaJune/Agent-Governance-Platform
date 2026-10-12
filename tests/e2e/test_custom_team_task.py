from __future__ import annotations

from fastapi.testclient import TestClient

from agentgov.app import create_app


def test_custom_team_task_runs_to_auditable_artifacts_and_reusable_template(tmp_path):
    db = f"sqlite:///{tmp_path / 'custom-team.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))

    response = client.post(
        "/tasks/dispatch-ad-hoc-team",
        json={
            "leader": "story_writer",
            "members": ["story_writer", "story_reviewer"],
            "title": "可审计写作与评价任务",
            "input_summary": "写一个短故事到文件，再让另一个 Agent 评价并输出评价文件",
            "strategy": "sequential_artifact_review",
            "execute_mode": "enqueue",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["matching"]["score"] == 1
    assert payload["team_snapshot"]["session_id"] == payload["session_id"]

    while True:
        tick = client.post("/worker/tick").json()
        if tick["processed"] == 0:
            break

    detail = client.get(f"/dashboard/sessions/{payload['session_id']}").json()
    assert detail["session"]["status"] == "completed"
    assert len(detail["runs"]) == 2
    assert len(detail["model_calls"]) == 2
    assert len(detail["tool_calls"]) >= 3
    assert len(detail["artifacts"]) >= 2
    assert any("story.md" in artifact["path"] for artifact in detail["artifacts"])
    assert any("review.md" in artifact["path"] for artifact in detail["artifacts"])
    assert any(message["message_type"] == "task.assigned" for message in detail["messages"])
    assert any(message["message_type"] == "task.result" for message in detail["messages"])

    template = client.post(
        f"/teams/templates/from-session/{payload['session_id']}",
        json={"name": "写作评价团队", "description": "由写作 Agent 和评价 Agent 组成的可复用团队"},
    )
    assert template.status_code == 200
    template_payload = template.json()
    assert template_payload["leader_agent_id"] == "story_writer"
    assert "story_reviewer" in template_payload["member_agent_ids"]
