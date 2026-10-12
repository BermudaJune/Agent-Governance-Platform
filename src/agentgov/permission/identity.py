from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IdentityContext:
    user_id: str | None = None
    api_key_id: str | None = None
    agent_id: str | None = None
    team_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    roles: list[str] = field(default_factory=list)
    delegated_by: str | None = None
    delegation_chain: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
