from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ProviderProtocol(str, Enum):
    openai = "openai"
    scripted = "scripted"


BUILTIN_CAPABILITY_IDS = {
    "repo.search",
    "repo.read",
    "repo.list",
    "file.read",
    "file.write",
    "command.local_readonly",
    "coordination.plan",
    "coordination.delegate",
    "review.content",
    "review.policy",
    "text.create",
    "external.weather",
    "visual.chart",
    "visual.diagram",
    "visual.image_brief",
    "office.spreadsheet",
    "office.presentation",
    "office.document",
    "office.pdf",
    "research.web",
    "research.citations",
    "data.analysis",
    "governance.trace",
}


class ProviderModelConfig(BaseModel):
    name: str
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0


class ProviderConfig(BaseModel):
    name: str
    protocol: ProviderProtocol
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    models: list[ProviderModelConfig] = Field(default_factory=list)
    script: str | None = None

    @model_validator(mode="after")
    def normalize_model_shortcut(self) -> "ProviderConfig":
        if self.model and not self.models:
            self.models = [ProviderModelConfig(name=self.model)]
        return self


class McpServerConfig(BaseModel):
    name: str
    command: str
    args: list[str] = Field(default_factory=list)


class SandboxConfig(BaseModel):
    id: str
    runtime: str = "local_readonly"
    filesystem: str = "read_only"
    network: str = "disabled"
    allowed_commands: list[str] = Field(default_factory=list)
    root: str = "."
    timeout_seconds: int = 20


class PolicyConfig(BaseModel):
    id: str
    type: str
    max_usd: float | None = None
    when: dict[str, Any] = Field(default_factory=dict)


class RoleConfig(BaseModel):
    allow: list[str] = Field(default_factory=list)


class DelegationRuleConfig(BaseModel):
    can_delegate_to: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)


class PermissionConfig(BaseModel):
    roles: dict[str, RoleConfig] = Field(default_factory=dict)
    delegation: dict[str, DelegationRuleConfig] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    id: str
    name: str
    provider: str
    model: str
    tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    sandbox: str | None = None
    policies: list[str] = Field(default_factory=list)
    system_prompt: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TeamConfig(BaseModel):
    id: str
    leader: str
    members: list[str]
    collaboration_strategy: str = "leader_worker"
    capabilities: list[str] = Field(default_factory=list)
    description: str = ""
    version: int = 1


class CapabilityConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "read"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)
    sandbox: str | None = None
    requires_approval: bool = False
    suitable_roles: list[str] = Field(default_factory=list)


class ToolConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "read"
    executor: str = "builtin"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    sandbox: str | None = None
    requires_approval: bool = False
    is_concurrency_safe: bool = False
    should_defer: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class SkillConfig(BaseModel):
    id: str
    name: str
    description: str = ""
    prompt_body: str = ""
    recommended_tools: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    source: str = "local"
    source_url: str | None = None
    version: str = "1.0.0"
    trust_level: str = "local"
    install_mode: str = "metadata_only"
    source_ref: str | None = None
    content_hash: str | None = None
    scan_status: str = "unscanned"
    scan_findings: list[str] = Field(default_factory=list)
    license: str | None = None
    category: str = "general"
    tags: list[str] = Field(default_factory=list)


class RelationalConfig(BaseModel):
    backend: Literal["sqlite"] = "sqlite"
    url: str = "sqlite:///./data/agentgov.db"


class InfrastructureConfig(BaseModel):
    relational: RelationalConfig = Field(default_factory=RelationalConfig)
    event_bus: dict[str, Any] = Field(default_factory=lambda: {"backend": "memory"})
    cache: dict[str, Any] = Field(default_factory=lambda: {"backend": "db"})
    object_store: dict[str, Any] = Field(default_factory=lambda: {"backend": "local", "root": "./data/objects"})
    vector_store: dict[str, Any] = Field(default_factory=lambda: {"backend": "sqlite_fts"})


class PlatformConfig(BaseModel):
    environment: str = "local"
    providers: list[ProviderConfig]
    mcp_servers: list[McpServerConfig] = Field(default_factory=list)
    sandboxes: list[SandboxConfig] = Field(default_factory=list)
    policies: list[PolicyConfig] = Field(default_factory=list)
    capabilities: list[CapabilityConfig] = Field(default_factory=list)
    tools: list[ToolConfig] = Field(default_factory=list)
    skills: list[SkillConfig] = Field(default_factory=list)
    permissions: PermissionConfig = Field(default_factory=PermissionConfig)
    agents: list[AgentConfig]
    teams: list[TeamConfig] = Field(default_factory=list)
    storage: InfrastructureConfig = Field(default_factory=InfrastructureConfig)
    budgets: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "PlatformConfig":
        provider_names = {p.name for p in self.providers}
        sandbox_ids = {s.id for s in self.sandboxes}
        policy_ids = {p.id for p in self.policies}
        agent_ids = {a.id for a in self.agents}
        capability_ids = {c.id for c in self.capabilities} | BUILTIN_CAPABILITY_IDS
        skill_ids = {s.id for s in self.skills}
        tool_ids = {t.id for t in self.tools} | {
            "repo_search",
            "repo_read",
            "repo_list",
            "file_read",
            "file_write",
            "local_command",
            "weather_lookup",
            "mermaid_render",
            "matplotlib_chart",
            "spreadsheet_write",
            "spreadsheet_validate",
            "pptx_generate",
            "pptx_validate",
            "document_generate",
            "pdf_export",
            "pdf_validate",
            "csv_analyze",
            "sqlite_query",
        }

        for agent in self.agents:
            if agent.provider not in provider_names:
                raise ValueError(f"agent {agent.id} references missing provider {agent.provider}")
            if agent.sandbox and agent.sandbox not in sandbox_ids:
                raise ValueError(f"agent {agent.id} references missing sandbox {agent.sandbox}")
            missing = [p for p in agent.policies if p not in policy_ids]
            if missing:
                raise ValueError(f"agent {agent.id} references missing policies {missing}")
            missing_skills = [s for s in agent.skills if s not in skill_ids]
            if missing_skills:
                raise ValueError(f"agent {agent.id} references missing skills {missing_skills}")
            missing_capabilities = [c for c in agent.capabilities if c not in capability_ids]
            if missing_capabilities:
                raise ValueError(f"agent {agent.id} references missing capabilities {missing_capabilities}")
            missing_tools = [t for t in agent.tools if t not in tool_ids]
            if missing_tools:
                raise ValueError(f"agent {agent.id} references missing tools {missing_tools}")

        for team in self.teams:
            if team.leader not in agent_ids:
                raise ValueError(f"team {team.id} references missing leader {team.leader}")
            missing_members = [m for m in team.members if m not in agent_ids]
            if missing_members:
                raise ValueError(f"team {team.id} references missing members {missing_members}")
            missing_capabilities = [c for c in team.capabilities if c not in capability_ids]
            if missing_capabilities:
                raise ValueError(f"team {team.id} references missing capabilities {missing_capabilities}")

        for skill in self.skills:
            missing_capabilities = [c for c in skill.capability_ids if c not in capability_ids]
            if missing_capabilities:
                raise ValueError(f"skill {skill.id} references missing capabilities {missing_capabilities}")

        return self
