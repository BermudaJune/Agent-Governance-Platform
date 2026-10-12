from __future__ import annotations

from agentgov.event_stream.stream import EventStream
from agentgov.sandbox.local_readonly import LocalReadOnlySandboxRuntime
from agentgov.storage.repositories import Repository


class SandboxService:
    def __init__(self, repo: Repository, events: EventStream, runtime: LocalReadOnlySandboxRuntime):
        self.repo = repo
        self.events = events
        self.runtime = runtime

    def execute(self, run_id: str, session_id: str, agent_id: str, command: list[str]) -> dict:
        step = self.events.append(run_id, session_id, "sandbox.action.started", "agent", agent_id, "started", {"command": command})
        result = self.runtime.execute(command)
        self.repo.insert_generic(
            "sandbox_actions",
            {
                "run_id": run_id,
                "step_id": step.id,
                "sandbox_id": "readonly",
                "action_type": "command",
                "command_summary": " ".join(command),
                "filesystem_policy": "read_only",
                "network_policy": "disabled",
                "status": result.status,
                "output_summary": result.output,
                "error": result.error,
                "duration_ms": result.duration_ms,
            },
        )
        self.events.append(run_id, session_id, "sandbox.action.finished", "agent", agent_id, result.status, {"command": command, "output": result.output, "error": result.error})
        return result.__dict__
