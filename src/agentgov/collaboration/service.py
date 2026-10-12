from __future__ import annotations

from agentgov.collaboration.leader_worker import LeaderWorkerStrategy
from agentgov.collaboration.team_bus import TeamBus
from agentgov.storage.repositories import Repository


class CollaborationService:
    def __init__(self, repo: Repository):
        self.bus = TeamBus(repo)
        self.leader_worker = LeaderWorkerStrategy(repo, self.bus)
