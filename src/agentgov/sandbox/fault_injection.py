from __future__ import annotations

from agentgov.sandbox.base import SandboxResult


class FaultInjectionSandboxRuntime:
    def __init__(self, mode: str):
        self.mode = mode

    def execute(self, command: list[str], cwd: str | None = None) -> SandboxResult:
        if self.mode == "timeout":
            return SandboxResult("timeout", "", "injected timeout", 1)
        if self.mode == "denied":
            return SandboxResult("denied", "", "injected permission denied", 1)
        return SandboxResult("failed", "", "injected failure", 1)
