from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


@dataclass
class SessionRecord:
    title: str
    owner_id: str
    root_agent_id: str | None = None
    team_id: str | None = None
    status: str = "idle"
    context_summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class RunRecord:
    session_id: str
    agent_id: str
    input_summary: str
    parent_run_id: str | None = None
    agent_version_id: str | None = None
    run_type: str = "agent"
    status: str = "pending"
    output_summary: str | None = None
    error: str | None = None
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)


@dataclass
class RunStep:
    run_id: str
    session_id: str
    seq: int
    event_type: str
    actor_type: str
    actor_id: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    parent_step_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
