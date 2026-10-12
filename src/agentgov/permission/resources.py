from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ResourceRef:
    resource_type: str
    resource_id: str
    owner_id: str | None = None
    team_id: str | None = None
    environment: str | None = None
    labels: dict[str, str] = field(default_factory=dict)
