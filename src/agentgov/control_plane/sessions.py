from __future__ import annotations

from agentgov.storage.models import SessionRecord
from agentgov.storage.repositories import Repository


class SessionService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def create(self, title: str, owner_id: str, root_agent_id: str | None = None, team_id: str | None = None) -> SessionRecord:
        return self.repo.create_session(SessionRecord(title=title, owner_id=owner_id, root_agent_id=root_agent_id, team_id=team_id))

    def get(self, session_id: str):
        return self.repo.get_session(session_id)
