from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyDecisionResult:
    decision: str
    policy_id: str
    policy_type: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.decision == "allow"
