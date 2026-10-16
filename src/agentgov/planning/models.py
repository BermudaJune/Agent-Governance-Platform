from __future__ import annotations

from pydantic import BaseModel, Field


class TaskNodeSpec(BaseModel):
    node_key: str
    assigned_agent_id: str
    title: str
    instruction: str
    node_type: str = "agent_task"
    required_capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    output_contract: dict[str, object] = Field(default_factory=dict)
