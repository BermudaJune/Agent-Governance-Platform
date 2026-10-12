from __future__ import annotations

from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.event_stream.stream import EventStream
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class SkillGateway:
    def __init__(self, repo: Repository, events: EventStream, registry: CapabilityRegistry):
        self.repo = repo
        self.events = events
        self.registry = registry

    def load_skill(self, run_id: str, session_id: str, agent_id: str, skill_id: str) -> dict:
        agent = self.registry.agent(agent_id)
        skill = self.registry.get_skill(skill_id)
        if skill is None:
            self.events.append(run_id, session_id, "skill.load.failed", "agent", agent_id, "failed", {"skill_id": skill_id, "reason": "unknown skill"})
            return {"status": "failed", "error": f"unknown skill: {skill_id}"}
        if agent is None or skill_id not in agent.skills:
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
