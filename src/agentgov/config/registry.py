from __future__ import annotations

from dataclasses import dataclass

from agentgov.config.schema import AgentConfig, PlatformConfig, ProviderConfig, TeamConfig


@dataclass(frozen=True)
class ConfigRegistry:
    config: PlatformConfig

    def provider(self, name: str) -> ProviderConfig:
        for provider in self.config.providers:
            if provider.name == name:
                return provider
        raise KeyError(f"unknown provider: {name}")

    def agent(self, agent_id: str) -> AgentConfig:
        for agent in self.config.agents:
            if agent.id == agent_id:
                return agent
        raise KeyError(f"unknown agent: {agent_id}")

    def team(self, team_id: str) -> TeamConfig:
        for team in self.config.teams:
            if team.id == team_id:
                return team
        raise KeyError(f"unknown team: {team_id}")


def build_registry(config: PlatformConfig) -> ConfigRegistry:
    return ConfigRegistry(config=config)
