from __future__ import annotations

from agentgov.storage.repositories import Repository
from agentgov.testing.qualification_scenario import run_qualification


def test_qualification_scenario(tmp_path):
    db = f"sqlite:///{tmp_path / 'qualification.db'}"
    result = run_qualification("config/examples/qualification.yaml", db)
    assert result.status == "completed"
    assert len(result.child_run_ids) == 4
    assert all(result.checks.values())

    repo = Repository(db)
    assert repo.get_run(result.parent_run_id)["status"] == "completed"
    assert repo.query_all("agent_messages")
    assert repo.query_all("experience_candidates", "WHERE source_run_id = ?", (result.parent_run_id,))
