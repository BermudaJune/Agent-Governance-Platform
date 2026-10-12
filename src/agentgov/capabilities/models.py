from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "read"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    is_concurrency_safe: bool = False
    should_defer: bool = False
    risk_level: str = "low"
    sandbox: str | None = None


class SkillDefinition(BaseModel):
    id: str
    name: str
    description: str = ""
    prompt_body: str = ""
    recommended_tools: list[str] = Field(default_factory=list)
    output_artifacts: list[str] = Field(default_factory=list)
    capability_ids: list[str] = Field(default_factory=list)
    risk_level: str = "low"


class CapabilityDefinition(BaseModel):
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


class TaskRequirement(BaseModel):
    task_summary: str
    required_capabilities: list[str] = Field(default_factory=list)
    required_roles: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    risk_hints: list[str] = Field(default_factory=list)
    path_requirements: list[str] = Field(default_factory=list)
    network_requirements: list[str] = Field(default_factory=list)
