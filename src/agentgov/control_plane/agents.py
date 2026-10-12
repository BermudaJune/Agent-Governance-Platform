from __future__ import annotations

from agentgov.config.schema import AgentConfig, PlatformConfig


class AgentRegistry:
    def __init__(self, config: PlatformConfig):
        self.agents = {agent.id: agent for agent in config.agents}

    def get(self, agent_id: str) -> AgentConfig:
        return self.agents[agent_id]

    def list(self) -> list[AgentConfig]:
        return list(self.agents.values())
