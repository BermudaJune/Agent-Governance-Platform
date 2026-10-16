from __future__ import annotations

from typing import Any
from threading import RLock

from agentgov.config.loader import load_config
from agentgov.gateway.tool_registry import builtin_tool_specs
from agentgov.storage.models import new_id, now_iso
from agentgov.storage.repositories import Repository


class DynamicGovernanceService:
    """Session-scoped runtime governance for Leader delegation and grants."""

    _decision_lock = RLock()

    def __init__(self, repo: Repository, config_path: str):
        self.repo = repo
        self.config_path = config_path

    def _config(self):
        return load_config(self.config_path)

    def _tool_ids(self) -> set[str]:
        cfg = self._config()
        return {tool.id for tool in cfg.tools} | {spec.id for spec in builtin_tool_specs()}

    def _skill_map(self) -> dict[str, Any]:
        return {skill.id: skill for skill in self._config().skills}

    def ensure_root(self, session_id: str) -> dict[str, Any] | None:
        session = self.repo.get_session(session_id)
        if not session or not session.get("root_agent_id"):
            return None
        current = self.repo.list_session_agents(session_id)
        existing = next((item for item in current if item["agent_id"] == session["root_agent_id"]), None)
        if existing:
            return existing
        return self._create_agent(
            session_id=session_id,
            agent_id=session["root_agent_id"],
            parent_agent_id=None,
            role="leader",
            origin="reused",
            depth=0,
            spec_snapshot=self._agent_snapshot(session["root_agent_id"]),
            created_by="system",
        )

    def list_agents(self, session_id: str) -> list[dict[str, Any]]:
        self.ensure_root(session_id)
        return self.repo.list_session_agents(session_id)

    def _agent_snapshot(self, agent_id: str) -> dict[str, Any]:
        agent = next((item for item in self._config().agents if item.id == agent_id), None)
        return agent.model_dump() if agent else {"id": agent_id}

    def _create_agent(self, *, session_id: str, agent_id: str, parent_agent_id: str | None, role: str,
                      origin: str, depth: int, spec_snapshot: dict[str, Any], created_by: str) -> dict[str, Any]:
        row_id = self.repo.insert_generic(
            "session_agents",
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "parent_agent_id": parent_agent_id,
                "role": role,
                "origin": origin,
                "depth": depth,
                "status": "active",
                "spec_snapshot": spec_snapshot,
                "created_by": created_by,
                "created_at": now_iso(),
            },
        )
        self._event(session_id, agent_id, "agent.created", created_by, {"origin": origin, "role": role, "parent_agent_id": parent_agent_id})
        return next(item for item in self.repo.list_session_agents(session_id) if item["id"] == row_id)

    def _event(self, session_id: str, agent_id: str, event_type: str, actor_id: str, payload: dict[str, Any]) -> str:
        return self.repo.insert_generic(
            "agent_lifecycle_events",
            {
                "session_id": session_id,
                "agent_id": agent_id,
                "event_type": event_type,
                "actor_id": actor_id,
                "payload": payload,
                "created_at": now_iso(),
            },
        )

    def _risk(self, skill_ids: list[str], tool_ids: list[str]) -> str:
        skill_map = self._skill_map()
        cfg = self._config()
        tools = {tool.id: tool for tool in cfg.tools}
        risk_levels = [skill_map[item].risk_level for item in skill_ids if item in skill_map]
        risk_levels += [tools[item].risk_level for item in tool_ids if item in tools]
        # Built-ins are intentionally conservative when no config override exists.
        if set(tool_ids) & {"file_write", "local_command", "http_get", "weather_lookup"}:
            return "high"
        if any(level == "high" for level in risk_levels):
            return "high"
        if any(level == "medium" for level in risk_levels):
            return "medium"
        if any(spec.id in tool_ids and spec.requires_approval for spec in builtin_tool_specs()):
            return "high"
        return "low"

    def create_delegation(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        session = self.repo.get_session(session_id)
        if not session:
            raise ValueError(f"unknown session: {session_id}")
        root = self.ensure_root(session_id)
        parent_agent_id = payload.get("parent_agent_id") or (root or {}).get("agent_id") or session.get("root_agent_id")
        if not parent_agent_id:
            raise ValueError("session has no Leader; set root_agent_id first")
        active_agents = self.repo.list_session_agents(session_id)
        parent = next((item for item in active_agents if item["agent_id"] == parent_agent_id and item["status"] == "active"), None)
        if not parent:
            raise ValueError("parent Agent is not active in this Session")
        skill_ids = list(dict.fromkeys(payload.get("requested_skills") or []))
        tool_ids = list(dict.fromkeys(payload.get("requested_tools") or []))
        unknown_skills = sorted(set(skill_ids) - set(self._skill_map()))
        unknown_tools = sorted(set(tool_ids) - self._tool_ids())
        if unknown_skills or unknown_tools:
            raise ValueError(f"unknown capabilities: skills={unknown_skills}, tools={unknown_tools}")
        max_depth = int(session.get("metadata", {}).get("governance", {}).get("max_depth", 3))
        depth = int(parent.get("depth", 0)) + 1
        reuses_active = any(item["agent_id"] == payload.get("requested_agent_id") and item["status"] == "active" for item in active_agents)
        if not reuses_active and depth > max_depth:
            raise ValueError(f"delegation depth exceeds limit {max_depth}")
        active_count = len([item for item in active_agents if item["status"] == "active"])
        max_agents = int(session.get("metadata", {}).get("governance", {}).get("max_agents", 12))
        if not reuses_active and active_count >= max_agents:
            raise ValueError(f"session Agent limit reached: {max_agents}")
        risk_level = self._risk(skill_ids, tool_ids)
        request_id = self.repo.insert_generic(
            "delegation_requests",
            {
                "session_id": session_id,
                "run_id": payload.get("run_id"),
                "requester_agent_id": payload.get("requester_agent_id") or parent_agent_id,
                "parent_agent_id": parent_agent_id,
                "requested_agent_id": payload.get("requested_agent_id"),
                "requested_role": payload.get("requested_role") or "specialist",
                "objective": payload.get("objective") or "Complete delegated work",
                "requested_skills": skill_ids,
                "requested_tools": tool_ids,
                "budget_usd": float(payload.get("budget_usd") or 0),
                "risk_level": risk_level,
                "status": "pending",
                "reason": payload.get("reason"),
                "created_at": now_iso(),
            },
        )
        self._event(session_id, parent_agent_id, "delegation.requested", parent_agent_id, {"request_id": request_id, "risk_level": risk_level, "skills": skill_ids, "tools": tool_ids})
        request = next(item for item in self.repo.list_delegation_requests(session_id) if item["id"] == request_id)
        if risk_level == "low" and payload.get("auto_approve", True):
            return self.decide(request_id, True, "system", "low-risk request auto-approved")
        approval_id = self.repo.insert_generic(
            "approvals",
            {
                "run_id": payload.get("run_id") or f"delegation:{request_id}",
                "step_id": None,
                "requested_by": parent_agent_id,
                "status": "pending",
                "action_summary": {"type": "delegation", "request_id": request_id, "role": request["requested_role"], "skills": skill_ids, "tools": tool_ids, "risk_level": risk_level, "requirement_id": (self.repo.get_current_requirement(session_id) or {}).get("id")},
                "reason": request["objective"],
                "created_at": now_iso(),
            },
        )
        self.repo.update_generic("delegation_requests", request_id, {"approval_id": approval_id})
        return {**request, "approval_id": approval_id}

    def decide(self, request_id: str, approved: bool, approver_id: str, reason: str | None = None) -> dict[str, Any]:
        with self._decision_lock:
            return self._decide(request_id, approved, approver_id, reason)

    def _decide(self, request_id: str, approved: bool, approver_id: str, reason: str | None = None) -> dict[str, Any]:
        rows = self.repo.query_all("delegation_requests", "WHERE id = ?", (request_id,))
        if not rows:
            raise KeyError(request_id)
        request = rows[0]
        if request["status"] != "pending":
            if request["status"] == ("approved" if approved else "rejected"):
                return {"request": request, "already_decided": True}
            raise ValueError("该扩展请求已处理或已过期，请刷新后查看当前规划")
        if request.get("approval_id"):
            approval = self.repo.query_all("approvals", "WHERE id = ?", (request["approval_id"],))[0]
            requirement_id = approval.get("action_summary", {}).get("requirement_id")
            if requirement_id and requirement_id != (self.repo.get_current_requirement(request["session_id"]) or {}).get("id"):
                raise ValueError("需求已变更，此扩展请求已过期，请让 Leader 重新规划")
        status = "approved" if approved else "rejected"
        self.repo.update_generic("delegation_requests", request_id, {"status": status, "reason": reason or request.get("reason"), "decided_at": now_iso()})
        if request.get("approval_id"):
            self.repo.update_generic("approvals", request["approval_id"], {"status": status, "approver_id": approver_id, "reason": reason, "decided_at": now_iso()})
        self._event(request["session_id"], request["parent_agent_id"], f"delegation.{status}", approver_id, {"request_id": request_id, "reason": reason})
        if not approved:
            return next(item for item in self.repo.list_delegation_requests(request["session_id"]) if item["id"] == request_id)
        active = self.repo.list_session_agents(request["session_id"])
        agent = next((item for item in active if item["agent_id"] == request.get("requested_agent_id") and item["status"] == "active"), None)
        if not agent:
            parent = next((item for item in active if item["agent_id"] == request["parent_agent_id"]), None)
            agent_id = request.get("requested_agent_id") or f"dynamic:{request['session_id'][:8]}:{request['requested_role']}:{new_id()[:8]}"
            snapshot = self._agent_snapshot(agent_id) if request.get("requested_agent_id") else {
                "id": agent_id,
                "name": request["requested_role"],
                "provider": (parent or {}).get("spec_snapshot", {}).get("provider", "inherited"),
                "model": (parent or {}).get("spec_snapshot", {}).get("model", "inherited"),
                "skills": request.get("requested_skills", []),
                "tools": request.get("requested_tools", []),
            }
            agent = self._create_agent(session_id=request["session_id"], agent_id=agent_id, parent_agent_id=request["parent_agent_id"], role=request["requested_role"], origin="reused" if request.get("requested_agent_id") else "dynamic", depth=(parent or {}).get("depth", 0) + 1, spec_snapshot=snapshot, created_by=request["requester_agent_id"])
        for skill_id in request.get("requested_skills", []):
            skill = self._skill_map()[skill_id]
            self.repo.insert_generic("session_skill_grants", {"session_id": request["session_id"], "agent_id": agent["agent_id"], "skill_id": skill_id, "version": skill.version, "source": f"delegation:{request_id}", "granted_by": approver_id, "status": "active", "created_at": now_iso()})
            self._event(request["session_id"], agent["agent_id"], "skill.granted", approver_id, {"request_id": request_id, "skill_id": skill_id, "version": skill.version})
        for tool_id in request.get("requested_tools", []):
            self.repo.insert_generic("session_tool_grants", {"session_id": request["session_id"], "agent_id": agent["agent_id"], "tool_id": tool_id, "granted_by": approver_id, "status": "active", "created_at": now_iso()})
            self._event(request["session_id"], agent["agent_id"], "tool.granted", approver_id, {"request_id": request_id, "tool_id": tool_id})
        return {"request": next(item for item in self.repo.list_delegation_requests(request["session_id"]) if item["id"] == request_id), "agent": agent}

    def retire(self, session_id: str, agent_id: str, actor_id: str, reason: str | None = None) -> dict[str, Any]:
        rows = [item for item in self.repo.list_session_agents(session_id) if item["agent_id"] == agent_id and item["status"] == "active"]
        if not rows:
            raise ValueError("active session Agent not found")
        self.repo.update_generic("session_agents", rows[0]["id"], {"status": "retired", "retired_at": now_iso()})
        self.repo.query_all("session_skill_grants", "WHERE session_id = ? AND agent_id = ?", (session_id, agent_id))
        with_grants = self.repo.query_all("session_tool_grants", "WHERE session_id = ? AND agent_id = ?", (session_id, agent_id))
        for grant in self.repo.query_all("session_skill_grants", "WHERE session_id = ? AND agent_id = ? AND status = 'active'", (session_id, agent_id)):
            self.repo.update_generic("session_skill_grants", grant["id"], {"status": "revoked"})
        for grant in with_grants:
            if grant["status"] == "active":
                self.repo.update_generic("session_tool_grants", grant["id"], {"status": "revoked"})
        self._event(session_id, agent_id, "agent.retired", actor_id, {"reason": reason or "operator action"})
        return next(item for item in self.repo.list_session_agents(session_id) if item["id"] == rows[0]["id"])

    def request_capability(self, session_id: str, agent_id: str, kind: str, capability_id: str, requester: str | None = None) -> dict[str, Any]:
        if agent_id not in {item["agent_id"] for item in self.list_agents(session_id)}:
            raise ValueError("Agent is not part of this Session")
        payload = {"parent_agent_id": agent_id, "requester_agent_id": requester or agent_id, "requested_agent_id": agent_id, "requested_role": f"{kind}_grant", "objective": f"Grant {kind} {capability_id}", "requested_skills": [capability_id] if kind == "skill" else [], "requested_tools": [capability_id] if kind == "tool" else [], "auto_approve": False}
        return self.create_delegation(session_id, payload)
