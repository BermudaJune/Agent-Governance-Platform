from __future__ import annotations

from agentgov.config.schema import PlatformConfig, TeamConfig


class TeamRegistry:
    def __init__(self, config: PlatformConfig):
        self.teams = {team.id: team for team in config.teams}

    def get(self, team_id: str) -> TeamConfig:
        return self.teams[team_id]
