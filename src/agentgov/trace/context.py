from __future__ import annotations

from dataclasses import dataclass, field
from agentgov.storage.models import new_id


@dataclass
class TraceContext:
    session_id: str
    run_id: str
    parent_run_id: str | None = None
    trace_id: str = field(default_factory=new_id)
    span_id: str | None = None
    parent_span_id: str | None = None
