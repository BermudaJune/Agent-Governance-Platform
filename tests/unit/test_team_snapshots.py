from __future__ import annotations

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.config.loader import load_config
from agentgov.storage.db import init_db
from agentgov.storage.models import SessionRecord
from agentgov.storage.repositories import Repository
from agentgov.teams.snapshots import TeamSnapshotService


def test_team_snapshot_can_be_saved_as_template(tmp_path):
    db = f"sqlite:///{tmp_path / 'team.db'}"
    init_db(db)
    repo = Repository(db)
    registry = CapabilityRegistry(load_config("config/examples/local.scripted.yaml"))
    service = TeamSnapshotService(repo, registry)
    session = repo.create_session(SessionRecord(title="team", owner_id="test", root_agent_id="story_writer"))

    snapshot = service.create_snapshot(
        session_id=session.id,
        leader_agent_id="story_writer",
        member_agent_ids=["story_writer", "story_reviewer"],
        collaboration_strategy="sequential_artifact_review",
    )
    template = service.save_template_from_session(session.id, "Story Team")

    assert snapshot.session_id == session.id
    assert template.leader_agent_id == "story_writer"
    assert "story_reviewer" in template.member_agent_ids
    assert repo.get_team_snapshot_for_session(session.id)["id"] == snapshot.id
