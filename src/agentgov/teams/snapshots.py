from __future__ import annotations

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository
from agentgov.teams.models import SessionTeamSnapshot, TeamTemplate


class TeamSnapshotService:
    def __init__(self, repo: Repository, registry: CapabilityRegistry):
        self.repo = repo
        self.registry = registry

    def create_snapshot(
        self,
        *,
        session_id: str,
        leader_agent_id: str,
        member_agent_ids: list[str],
        collaboration_strategy: str,
        matching_report_id: str | None = None,
        source_team_template_id: str | None = None,
    ) -> SessionTeamSnapshot:
        members = list(dict.fromkeys([leader_agent_id, *member_agent_ids]))
        snapshot = SessionTeamSnapshot(
            session_id=session_id,
            source_team_template_id=source_team_template_id,
            leader_agent_id=leader_agent_id,
            member_agent_ids=members,
            agent_capabilities={agent_id: self.registry.agent_capability_ids(agent_id) for agent_id in members},
            collaboration_strategy=collaboration_strategy,
            matching_report_id=matching_report_id,
        )
        self.repo.insert_team_snapshot(snapshot.model_dump())
        return snapshot

    def save_template_from_session(self, session_id: str, name: str, description: str = "") -> TeamTemplate:
        snapshot = self.repo.get_team_snapshot_for_session(session_id)
        if snapshot is None:
            raise KeyError(f"session has no team snapshot: {session_id}")
        capability_ids: set[str] = set()
        for values in (snapshot.get("agent_capabilities") or {}).values():
            capability_ids.update(values)
        template = TeamTemplate(
            name=name,
            leader_agent_id=snapshot["leader_agent_id"],
            member_agent_ids=snapshot["member_agent_ids"],
            collaboration_strategy=snapshot["collaboration_strategy"],
            capability_ids=sorted(capability_ids),
            description=description,
            updated_at=now_iso(),
        )
        self.repo.insert_team_template(template.model_dump())
        return template
