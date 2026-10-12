from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SandboxResult:
    status: str
    output: str
    error: str | None = None
    duration_ms: int = 0
