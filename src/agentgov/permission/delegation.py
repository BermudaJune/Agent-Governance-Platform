from __future__ import annotations

from dataclasses import dataclass, field
from agentgov.storage.models import new_id, now_iso


@dataclass
class DelegationGrant:
    parent_run_id: str
    grantee_agent_id: str
    granted_by: str
    allowed_actions: list[str] = field(default_factory=list)
    allowed_resources: list[str] = field(default_factory=list)
    expires_at: str | None = None
    status: str = "active"
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=now_iso)
