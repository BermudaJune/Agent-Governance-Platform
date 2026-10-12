from __future__ import annotations

from agentgov.sandbox.service import SandboxService


class LocalCommandTools:
    def __init__(self, sandbox: SandboxService):
        self.sandbox = sandbox

    def call(self, run_id: str, session_id: str, agent_id: str, command: list[str]) -> dict:
        return self.sandbox.execute(run_id, session_id, agent_id, command)
