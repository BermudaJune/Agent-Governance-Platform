from __future__ import annotations

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.config.loader import load_config
from agentgov.event_stream.stream import EventStream
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class SkillGateway:
    def __init__(self, repo: Repository, events: EventStream, registry: CapabilityRegistry, config_path: str | None = None):
        self.repo = repo
        self.events = events
        self.registry = registry
        self.config_path = config_path

    def _refresh(self):
        if self.config_path:
            self.registry = CapabilityRegistry(load_config(self.config_path))

    def load_skill(self, run_id: str, session_id: str, agent_id: str, skill_id: str) -> dict:
        self._refresh()
        agent = self.registry.agent(agent_id)
        skill = self.registry.get_skill(skill_id)
        if skill is None:
            self.events.append(run_id, session_id, "skill.load.failed", "agent", agent_id, "failed", {"skill_id": skill_id, "reason": "unknown skill"})
            return {"status": "failed", "error": f"unknown skill: {skill_id}"}
        session_grant = self.repo.query_all(
            "session_skill_grants",
            "WHERE session_id = ? AND agent_id = ? AND skill_id = ? AND status = 'active' LIMIT 1",
            (session_id, agent_id, skill_id),
        )
        if (agent is None and not session_grant) or (agent is not None and skill_id not in agent.skills and not session_grant):
            self.events.append(run_id, session_id, "skill.load.denied", "agent", agent_id, "denied", {"skill_id": skill_id})
            self.repo.insert_generic(
                "policy_decisions",
                {
                    "run_id": run_id,
                    "step_id": None,
                    "policy_id": "skill_allowlist",
                    "policy_type": "skill",
                    "subject": agent_id,
                    "action": "skill.load",
                    "resource": skill_id,
                    "decision": "deny",
                    "reason": "skill is not allowed for this agent",
                    "metadata": {},
                    "created_at": now_iso(),
                },
            )
            return {"status": "denied", "error": f"skill not allowed: {skill_id}"}
        self.events.append(run_id, session_id, "skill.loaded", "agent", agent_id, "completed", {"skill_id": skill_id})
        return {"status": "completed", "skill": skill.model_dump()}

    def context_for_agent(self, run_id: str, session_id: str, agent_id: str) -> str:
        self._refresh()
        agent = self.registry.agent(agent_id)
        static_ids = list(agent.skills) if agent else []
        grants = self.repo.query_all(
            "session_skill_grants",
            "WHERE session_id = ? AND agent_id = ? AND status = 'active'",
            (session_id, agent_id),
        )
        skill_ids = list(dict.fromkeys(static_ids + [str(item["skill_id"]) for item in grants]))
        sections: list[str] = []
        for skill_id in skill_ids:
            loaded = self.load_skill(run_id, session_id, agent_id, skill_id)
            if loaded.get("status") != "completed":
                continue
            skill = loaded.get("skill") or {}
            body = str(skill.get("prompt_body") or "").strip()
            if not body:
                continue
            sections.append(f"[Skill {skill_id} v{skill.get('version', 'unknown')}]\n{body[:8000]}")
        return "Governed skills available to this Agent:\n\n" + "\n\n".join(sections) if sections else ""
