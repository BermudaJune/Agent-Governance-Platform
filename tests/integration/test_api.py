from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agentgov.app import create_app
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


def test_api_smoke(tmp_path):
    db = f"sqlite:///{tmp_path / 'api.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    assert client.get("/health").json()["status"] == "ok"
    session = client.post("/sessions", json={"title": "api", "owner_id": "u"}).json()
    run = client.post("/runs", json={"session_id": session["id"], "agent_id": "coordinator", "input_summary": "hello"}).json()
    assert client.get(f"/runs/{run['id']}").json()["run"]["id"] == run["id"]
    assert client.get("/dashboard/overview").json()["runs"] == 1


def test_artifact_preview_download_and_session_path_isolation(tmp_path, monkeypatch):
    config = Path("config/examples/local.scripted.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    db = f"sqlite:///{tmp_path / 'artifacts.db'}"
    client = TestClient(create_app(database=db, config_path=str(config)))
    repo = Repository(db)
    first = client.post("/sessions", json={"title": "first", "owner_id": "u"}).json()
    second = client.post("/sessions", json={"title": "second", "owner_id": "u"}).json()
    run = client.post("/runs", json={"session_id": first["id"], "agent_id": "coordinator", "input_summary": "write"}).json()
    workspace = tmp_path / "data" / "workspaces" / first["id"]
    workspace.mkdir(parents=True)
    delivery = workspace / "delivery.md"
    delivery.write_text("verified delivery", encoding="utf-8")
    artifact_id = repo.insert_artifact({
        "session_id": first["id"], "run_id": run["id"], "created_by_agent_id": "coordinator",
        "artifact_type": "file", "path": str(delivery), "summary": "delivery",
        "metadata": {"mime_type": "text/markdown"}, "created_at": now_iso(),
    })

    preview = client.get(f"/sessions/{first['id']}/artifacts/{artifact_id}/preview")
    assert preview.status_code == 200
    assert preview.json()["content"] == "verified delivery"
    assert preview.json()["mime_type"] == "text/markdown"
    download = client.get(f"/sessions/{first['id']}/artifacts/{artifact_id}/download")
    assert download.content == b"verified delivery"
    assert "attachment" in download.headers["content-disposition"]
    assert client.get(f"/sessions/{second['id']}/artifacts/{artifact_id}/preview").status_code == 404

    unsafe = workspace / "page.html"
    unsafe.write_text("<script>alert(1)</script>", encoding="utf-8")
    unsafe_id = repo.insert_artifact({
        "session_id": first["id"], "run_id": run["id"], "created_by_agent_id": "coordinator",
        "artifact_type": "file", "path": str(unsafe), "summary": "html",
        "metadata": {"mime_type": "text/html"}, "created_at": now_iso(),
    })
    unsafe_preview = client.get(f"/sessions/{first['id']}/artifacts/{unsafe_id}/preview")
    assert unsafe_preview.json()["kind"] == "download"
    assert unsafe_preview.json()["mime_type"] == "application/octet-stream"
    assert client.get(f"/sessions/{first['id']}/artifacts/{unsafe_id}/content").status_code == 415

    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    outside_id = repo.insert_artifact({
        "session_id": first["id"], "run_id": run["id"], "created_by_agent_id": "coordinator",
        "artifact_type": "file", "path": str(outside), "summary": "invalid path",
        "metadata": {}, "created_at": now_iso(),
    })
    assert client.get(f"/sessions/{first['id']}/artifacts/{outside_id}/preview").status_code == 403


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


def test_session_knowledge_is_granted_and_audited(tmp_path):
    db = f"sqlite:///{tmp_path / 'knowledge.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    result = client.post(
        "/tasks/dispatch",
        json={
            "agent_id": "evidence",
            "input_summary": "summarize the supplied evidence",
            "execute_now": True,
            "knowledge_sources": [{
                "name": "验收约束",
                "source_type": "session_note",
                "content": "结果必须引用来源 ID。",
                "required_citation": True,
            }],
        },
    )

    assert result.status_code == 200
    session_id = result.json()["session_id"]
    detail = client.get(f"/dashboard/sessions/{session_id}").json()
    assert len(detail["knowledge_sources"]) == 1
    assert detail["knowledge_grants"][0]["agent_id"] == "evidence"
    assert any(event["action"] == "context_build" and event["decision"] == "allow" for event in detail["knowledge_access_events"])
    context = client.get(f"/runs/{result.json()['run_id']}/knowledge-context").json()
    assert context["sources"][0]["name"] == "验收约束"


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


def test_leader_can_create_dynamic_agent_with_session_grants(tmp_path):
    db = f"sqlite:///{tmp_path / 'dynamic.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    session = client.post(
        "/sessions",
        json={"title": "dynamic delegation", "owner_id": "u", "root_agent_id": "coordinator"},
    ).json()

    result = client.post(
        f"/sessions/{session['id']}/delegations",
        json={
            "objective": "collect repository evidence",
            "requested_role": "researcher",
            "requested_skills": ["repo.research"],
            "requested_tools": ["repo_search"],
        },
    )
    assert result.status_code == 200
    assert result.json()["request"]["status"] == "approved"
    detail = client.get(f"/dashboard/sessions/{session['id']}").json()
    assert len(detail["session_agents"]) == 2
    assert detail["session_agents"][1]["origin"] == "dynamic"
    assert detail["skill_grants"][0]["skill_id"] == "repo.research"
    assert detail["tool_grants"][0]["tool_id"] == "repo_search"

    graph = client.get(f"/dashboard/topology/sessions/{session['id']}").json()
    assert any(node["type"] == "session_agent" for node in graph["nodes"])
    assert any(node["type"] == "skill_grant" for node in graph["nodes"])
    assert any(edge["type"] == "agent_uses_skill" for edge in graph["edges"])


def test_high_risk_leader_delegation_requires_hitl(tmp_path):
    db = f"sqlite:///{tmp_path / 'dynamic-approval.db'}"
    client = TestClient(create_app(database=db, config_path="config/examples/local.scripted.yaml"))
    session = client.post(
        "/sessions",
        json={"title": "approval delegation", "owner_id": "u", "root_agent_id": "coordinator"},
    ).json()
    result = client.post(
        f"/sessions/{session['id']}/delegations",
        json={"objective": "write a report", "requested_role": "builder", "requested_tools": ["file_write"]},
    )
    assert result.status_code == 200
    payload = result.json()
    assert payload["status"] == "pending"
    approval_id = payload["approval_id"]
    assert client.get("/approvals").json()[0]["id"] == approval_id

    decided = client.post(
        f"/delegations/{payload['id']}/decide",
        json={"approved": True, "approver_id": "operator"},
    )
    assert decided.status_code == 200
    detail = client.get(f"/dashboard/sessions/{session['id']}").json()
    assert detail["delegation_requests"][0]["status"] == "approved"
    assert detail["tool_grants"][0]["tool_id"] == "file_write"


def test_skill_catalog_exposes_local_mewcode_and_rejects_non_github_scan(tmp_path, monkeypatch):
    skill_dir = tmp_path / ".mewcode" / "skills" / "local-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: local-skill\ndescription: A local skill\n---\nDo the work.\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "config.yaml"
    config.write_text(
        """
providers:
  - name: scripted
    protocol: scripted
    script: default
agents:
  - id: coordinator
    name: Coordinator
    provider: scripted
    model: scripted
""",
        encoding="utf-8",
    )
    client = TestClient(create_app(database=f"sqlite:///{tmp_path / 'skills.db'}", config_path=str(config)))

    skills = client.get("/skills").json()
    assert any(skill["id"] == "local.mewcode.local-skill" for skill in skills)
    result = client.post("/skills/github/scan", json={"url": "https://example.com/not-github"})
    assert result.status_code == 400


def test_skill_recommendation_matches_office_task(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        """
providers:
  - name: scripted
    protocol: scripted
    script: default
agents:
  - id: coordinator
    name: Coordinator
    provider: scripted
    model: scripted
""",
        encoding="utf-8",
    )
    client = TestClient(create_app(database=f"sqlite:///{tmp_path / 'recommend.db'}", config_path=str(config)))

    result = client.get("/skills/recommend", params={"task": "生成一份 Excel 报告和数据图"})

    assert result.status_code == 200
    payload = result.json()
    assert "office.spreadsheet" in payload["required_capabilities"]
    assert any(skill["id"] == "office.excel-report" for skill in payload["skills"])
