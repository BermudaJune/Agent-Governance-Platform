from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeSourceInput(BaseModel):
    name: str = "Session 知识"
    source_type: str = "session_note"
    content: str = ""
    locator: str | None = None
    trust_level: str = "session_input"
    required_citation: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgePolicy(BaseModel):
    allow_agent_search: bool = True
    require_citation: bool = True
    allow_upstream_artifacts: bool = True
