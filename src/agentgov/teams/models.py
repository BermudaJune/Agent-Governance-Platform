from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from agentgov.storage.models import new_id, now_iso


class TeamMatchingReport(BaseModel):
    id: str = Field(default_factory=new_id)
    session_id: str | None = None
    team_id: str | None = None
    score: float = 0.0
    decision: str = "adjust"
    covered_capabilities: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    redundant_agents: list[str] = Field(default_factory=list)
    suggested_agents: list[str] = Field(default_factory=list)
    risk_items: list[dict[str, Any]] = Field(default_factory=list)
    token_waste_warnings: list[str] = Field(default_factory=list)
    checker: str = "rules"
    explanation: str = ""
    created_at: str = Field(default_factory=now_iso)


class TeamTemplate(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    version: int = 1
    leader_agent_id: str
    member_agent_ids: list[str]
    collaboration_strategy: str = "leader_worker"
    capability_ids: list[str] = Field(default_factory=list)
    description: str = ""
    status: str = "active"
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)


class SessionTeamSnapshot(BaseModel):
    id: str = Field(default_factory=new_id)
    session_id: str
    source_team_template_id: str | None = None
    leader_agent_id: str
    member_agent_ids: list[str]
    agent_capabilities: dict[str, list[str]] = Field(default_factory=dict)
    collaboration_strategy: str = "leader_worker"
    matching_report_id: str | None = None
    created_at: str = Field(default_factory=now_iso)
