from __future__ import annotations

from agentgov.capabilities.models import CapabilityDefinition, SkillDefinition, ToolDefinition
from agentgov.config.schema import AgentConfig, PlatformConfig


DEFAULT_TOOL_CAPABILITIES: dict[str, CapabilityDefinition] = {
    "repo_search": CapabilityDefinition(
        id="repo.search",
        name="Repository Search",
        description="Search repository contents.",
        category="read",
        required_tools=["repo_search"],
        suitable_roles=["researcher", "evidence"],
    ),
    "repo_read": CapabilityDefinition(
        id="repo.read",
        name="Repository Read",
        description="Read repository files.",
        category="read",
        required_tools=["repo_read"],
        suitable_roles=["researcher", "evidence"],
    ),
    "repo_list": CapabilityDefinition(
        id="repo.list",
        name="Repository List",
        description="List repository files.",
        category="read",
        required_tools=["repo_list"],
        suitable_roles=["researcher", "evidence"],
    ),
    "file_read": CapabilityDefinition(
        id="file.read",
        name="File Read",
        description="Read session workspace files.",
        category="read",
        required_tools=["file_read"],
        suitable_roles=["reviewer", "writer"],
    ),
    "file_write": CapabilityDefinition(
        id="file.write",
        name="File Write",
        description="Write artifacts to a governed workspace.",
        category="write",
        risk_level="medium",
        required_tools=["file_write"],
        requires_approval=True,
        suitable_roles=["writer", "executor"],
    ),
    "local_command": CapabilityDefinition(
        id="command.local_readonly",
        name="Local Read-only Command",
        description="Run approved read-only commands in sandbox.",
        category="command",
        risk_level="medium",
        required_tools=["local_command"],
        sandbox="readonly",
        suitable_roles=["executor"],
    ),
    "weather_lookup": CapabilityDefinition(
        id="external.weather",
        name="Weather Lookup",
        description="Query current weather from an external provider.",
        category="network",
        risk_level="low",
        required_tools=["weather_lookup"],
        suitable_roles=["researcher", "writer"],
    ),
}

ROLE_CAPABILITIES: dict[str, list[str]] = {
    "coordinator": ["coordination.plan", "coordination.delegate"],
    "reviewer": ["review.content"],
    "policy_auditor": ["review.policy"],
    "story_writer": ["text.create", "file.write"],
    "story_reviewer": ["file.read", "review.content", "file.write"],
}


class CapabilityRegistry:
    def __init__(self, config: PlatformConfig):
        self.config = config
        self._capabilities: dict[str, CapabilityDefinition] = {}
        self._skills: dict[str, SkillDefinition] = {}
        self._tools: dict[str, ToolDefinition] = {}
        self._load()

    def _load(self) -> None:
        for item in self.config.capabilities:
            self._capabilities[item.id] = CapabilityDefinition.model_validate(item.model_dump())
        for item in DEFAULT_TOOL_CAPABILITIES.values():
            self._capabilities.setdefault(item.id, item)
        for capability_id in ("coordination.plan", "coordination.delegate", "review.content", "review.policy", "text.create", "external.weather"):
            self._capabilities.setdefault(
                capability_id,
                CapabilityDefinition(
                    id=capability_id,
                    name=capability_id.replace(".", " ").title(),
                    description=f"Inferred capability {capability_id}",
                    category="coordination" if capability_id.startswith("coordination") else "read",
                ),
            )
        for item in self.config.skills:
            self._skills[item.id] = SkillDefinition.model_validate(item.model_dump())
        for tool_name, capability in DEFAULT_TOOL_CAPABILITIES.items():
            self._tools[tool_name] = ToolDefinition(
                id=tool_name,
                name=tool_name,
                description=capability.description,
                category=capability.category,
                risk_level=capability.risk_level,
                sandbox=capability.sandbox,
            )
        for item in self.config.tools:
            self._tools[item.id] = ToolDefinition(
                id=item.id,
                name=item.name,
                description=item.description,
                category=item.category,
                input_schema=item.input_schema,
                output_schema=item.output_schema,
                is_concurrency_safe=item.is_concurrency_safe,
                should_defer=item.should_defer,
                risk_level=item.risk_level,
                sandbox=item.sandbox,
            )

    def list_capabilities(self) -> list[CapabilityDefinition]:
        return list(self._capabilities.values())

    def get_capability(self, capability_id: str) -> CapabilityDefinition | None:
        return self._capabilities.get(capability_id)

    def list_skills(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def agent(self, agent_id: str) -> AgentConfig | None:
        return next((agent for agent in self.config.agents if agent.id == agent_id), None)

    def list_agent_capabilities(self, agent_id: str) -> list[CapabilityDefinition]:
        agent = self.agent(agent_id)
        if agent is None:
            return []
        capability_ids: set[str] = set(agent.capabilities)
        for skill_id in agent.skills:
            skill = self._skills.get(skill_id)
            if skill:
                capability_ids.update(skill.capability_ids)
        for tool in agent.tools:
            capability = DEFAULT_TOOL_CAPABILITIES.get(tool)
            if capability:
                capability_ids.add(capability.id)
        capability_ids.update(ROLE_CAPABILITIES.get(agent.id, []))
        lowered_name = f"{agent.name} {agent.system_prompt}".lower()
        if "review" in lowered_name or "评价" in lowered_name or "评审" in lowered_name:
            capability_ids.add("review.content")
        if "写" in lowered_name or "writer" in lowered_name or "创作" in lowered_name:
            capability_ids.add("text.create")
        return [self._capabilities[cid] for cid in sorted(capability_ids) if cid in self._capabilities]

    def agent_capability_ids(self, agent_id: str) -> list[str]:
        return [item.id for item in self.list_agent_capabilities(agent_id)]
