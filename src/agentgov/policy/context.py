from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PolicyContext:
    run_id: str
    subject: str
    action: str
    resource: str
    attributes: dict[str, Any] = field(default_factory=dict)
