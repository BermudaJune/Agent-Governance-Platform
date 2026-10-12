from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agentgov.event_stream.stream import EventStream
from agentgov.gateway.tool_registry import ToolExecutionContext, ToolRegistry, builtin_tool_specs, is_workspace_relative_path
from agentgov.providers.local_repo_tools import LocalRepoTools
from agentgov.sandbox.service import SandboxService
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class ToolGateway:
    def __init__(
        self,
        repo: Repository,
        events: EventStream,
        registry: ToolRegistry | LocalRepoTools,
        sandbox: SandboxService | None = None,
        allowed_tools_by_agent: dict[str, list[str]] | Callable[[], dict[str, list[str]]] | None = None,
    ):
        self.repo = repo
        self.events = events
        if isinstance(registry, ToolRegistry):
            self.registry = registry
        else:
            self.registry = ToolRegistry(repo_tools=registry, sandbox=sandbox)
            for spec in builtin_tool_specs():
                self.registry.register(spec)
        self.allowed_tools_by_agent = allowed_tools_by_agent

    def schemas_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        allowed = self._allowed_tools()
        if allowed is None:
            return [spec.openai_tool() for spec in self.registry.list_specs()]
        return self.registry.schemas_for_tools(allowed.get(agent_id, []))

    def call(self, run_id: str, session_id: str, agent_id: str, tool_name: str, args: dict) -> dict:
        args = dict(args or {})
        tool_call_id = args.pop("tool_call_id", None)
        spec = self.registry.get(tool_name)
        intent_step = self.events.append(
            run_id,
            session_id,
            "action.intent.created",
            "agent",
            agent_id,
            "created",
            {
                "tool": tool_name,
                "tool_call_id": tool_call_id,
                "args": args,
                "category": spec.category if spec else "unknown",
                "risk_level": spec.risk_level if spec else "unknown",
            },
        )
        action_id = self.repo.insert_generic(
            "action_intents",
            {
                "run_id": run_id,
                "session_id": session_id,
                "step_id": intent_step.id,
                "agent_id": agent_id,
                "action_type": spec.category if spec else "unknown",
                "tool_name": tool_name,
                "arguments": args,
                "status": "created",
                "created_at": now_iso(),
            },
        )

        decision = self._preflight(agent_id, tool_name, args)
        decision_step = self.events.append(
            run_id,
            session_id,
            "policy.decision",
            "policy",
            "tool_policy",
            decision["decision"],
            {
                "action_id": action_id,
                "tool": tool_name,
                "agent_id": agent_id,
                "reason": decision["reason"],
                "metadata": decision.get("metadata", {}),
            },
        )
        decision_id = self.repo.insert_generic(
            "policy_decisions",
            {
                "run_id": run_id,
                "step_id": decision_step.id,
                "policy_id": decision["policy_id"],
                "policy_type": "permission",
                "subject": agent_id,
                "action": "tool.call",
                "resource": tool_name,
                "decision": decision["decision"],
                "reason": decision["reason"],
                "metadata": {"args": args, **decision.get("metadata", {})},
                "created_at": now_iso(),
            },
        )

        if decision["decision"] != "allow":
            result = {"status": "denied", "error": decision["reason"], "decision": decision["decision"], "action_id": action_id}
            self.repo.update_generic("action_intents", action_id, {"status": "denied", "policy_decision_id": decision_id})
            if decision["decision"] == "ask":
                approval_id = self.repo.insert_generic(
                    "approvals",
                    {
                        "run_id": run_id,
                        "step_id": decision_step.id,
                        "requested_by": agent_id,
                        "status": "pending",
                        "action_summary": {"tool": tool_name, "args": args, "action_id": action_id},
                        "reason": decision["reason"],
                        "created_at": now_iso(),
                    },
                )
                self.repo.update_run_status(run_id, "paused", error=decision["reason"])
                result = {
                    "status": "awaiting_approval",
                    "error": decision["reason"],
                    "approval_id": approval_id,
                    "action_id": action_id,
                }
            step = self.events.append(
                run_id,
                session_id,
                "tool.call.finished",
                "policy",
                "tool_policy",
                result["status"],
                {"tool": tool_name, "agent_id": agent_id, "reason": result["error"], "action_id": action_id},
            )
            self.repo.insert_generic(
                "tool_calls",
                {
                    "run_id": run_id,
                    "step_id": step.id,
                    "tool_name": tool_name,
                    "caller_agent_id": agent_id,
                    "args_summary": args,
                    "result_summary": result,
                    "status": result["status"],
                    "approval_id": result.get("approval_id"),
                },
            )
            return result

        self.repo.update_generic("action_intents", action_id, {"status": "allowed", "policy_decision_id": decision_id})
        self.events.append(run_id, session_id, "tool.call.started", "agent", agent_id, "started", {"tool": tool_name, "args": args, "action_id": action_id})
        try:
            result = self.registry.execute(spec, ToolExecutionContext(run_id, session_id, agent_id), args) if spec else {"status": "failed", "error": f"unknown tool {tool_name}"}
        except Exception as exc:
            result = {"status": "failed", "error": str(exc)}
        status = result.get("status", "completed")
        step = self.events.append(run_id, session_id, "tool.call.finished", "agent", agent_id, status, {"tool": tool_name, "args": args, "result": result, "action_id": action_id})
        self.repo.insert_generic(
            "tool_calls",
            {
                "run_id": run_id,
                "step_id": step.id,
                "tool_name": tool_name,
                "caller_agent_id": agent_id,
                "args_summary": args,
                "result_summary": result,
                "status": status,
            },
        )
        observation_id = self.repo.insert_generic(
            "observations",
            {
                "run_id": run_id,
                "step_id": step.id,
                "action_intent_id": action_id,
                "agent_id": agent_id,
                "content": self._summarize_observation(tool_name, result),
                "data": result,
                "status": status,
                "created_at": now_iso(),
            },
        )
        self.repo.update_generic("action_intents", action_id, {"status": status, "observation_id": observation_id})
        self.events.append(
            run_id,
            session_id,
            "observation.created",
            "tool",
            tool_name,
            status,
            {"action_id": action_id, "observation_id": observation_id, "summary": self._summarize_observation(tool_name, result)},
        )
        if tool_name in {"file_write", "file_read"} and result.get("path"):
            self.repo.insert_generic(
                "evidence_refs",
                {
                    "ref_type": "artifact" if tool_name == "file_write" else "file",
                    "ref_id": result["path"],
                    "run_id": run_id,
                    "step_id": step.id,
                    "path": result["path"],
                    "summary": f"{agent_id} {tool_name} {result.get('relative_path')}",
                },
            )
            if tool_name == "file_write" and status in {"completed", "ok"}:
                self.repo.insert_artifact(
                    {
                        "session_id": session_id,
                        "run_id": run_id,
                        "created_by_agent_id": agent_id,
                        "artifact_type": "file",
                        "path": result["path"],
                        "summary": f"{agent_id} wrote {result.get('relative_path') or result['path']}",
                        "metadata": {"tool": tool_name, "relative_path": result.get("relative_path")},
                        "created_at": now_iso(),
                    },
                )
        if status not in {"completed", "ok"}:
            self.events.append(
                run_id,
                session_id,
                "tool.call.failed",
                "agent",
                agent_id,
                "failed",
                {"tool": tool_name, "error": result.get("error"), "created_at": now_iso()},
            )
        return result

    def _preflight(self, agent_id: str, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        spec = self.registry.get(tool_name)
        if spec is None:
            return {"decision": "deny", "policy_id": "tool_registered", "reason": f"unknown tool {tool_name}"}
        allowed = self._allowed_tools()
        if allowed is not None and tool_name not in allowed.get(agent_id, []):
            return {
                "decision": "deny",
                "policy_id": "agent_tool_allowlist",
                "reason": f"agent {agent_id} is not allowed to call {tool_name}",
            }
        if spec.category in {"write", "read"} and tool_name in {"file_write", "file_read"}:
            path = str(args.get("path", ""))
            if not is_workspace_relative_path(path):
                return {
                    "decision": "ask",
                    "policy_id": "session_workspace_path",
                    "reason": "file tools must use a relative path inside the current Session workspace",
                    "metadata": {"path": path},
                }
        if spec.category == "network" and spec.allowed_domains:
            return {"decision": "allow", "policy_id": "network_domain_allowlist", "reason": f"network tool is restricted to {', '.join(spec.allowed_domains)}"}
        if spec.requires_approval or spec.risk_level == "high":
            return {"decision": "ask", "policy_id": "risk_requires_approval", "reason": f"{tool_name} requires human approval"}
        return {"decision": "allow", "policy_id": "tool_governance", "reason": "tool call passed registry, allowlist and argument preflight"}

    def _allowed_tools(self) -> dict[str, list[str]] | None:
        if callable(self.allowed_tools_by_agent):
            return self.allowed_tools_by_agent()
        return self.allowed_tools_by_agent

    def _summarize_observation(self, tool_name: str, result: dict[str, Any]) -> str:
        if result.get("status") not in {"completed", "ok"}:
            return f"{tool_name} failed: {result.get('error', 'unknown error')}"
        if tool_name == "weather_lookup":
            weather = result.get("weather", {})
            return f"weather {weather.get('location')}: {weather.get('description')}, {weather.get('temperature_c')}C"
        if tool_name == "file_write":
            return f"wrote {result.get('relative_path') or result.get('path')}"
        if tool_name == "file_read":
            return f"read {result.get('relative_path') or result.get('path')}"
        if tool_name == "local_command":
            return str(result.get("output", ""))[:500]
        return str(result)[:500]
