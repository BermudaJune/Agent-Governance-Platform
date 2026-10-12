from __future__ import annotations

from dataclasses import dataclass

from agentgov.config.schema import PermissionConfig
from agentgov.permission.identity import IdentityContext
from agentgov.permission.resources import ResourceRef
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


@dataclass
class PermissionCheck:
    identity: IdentityContext
    action: str
    resource: ResourceRef
    risk_level: str = "low"


class PermissionService:
    def __init__(self, repo: Repository, config: PermissionConfig):
        self.repo = repo
        self.config = config

    def allowed(self, check: PermissionCheck, run_id: str | None = None) -> bool:
        for role in check.identity.roles:
            role_cfg = self.config.roles.get(role)
            if role_cfg and ("*" in role_cfg.allow or check.action in role_cfg.allow):
                return True
        return False

    def record_decision(self, run_id: str, check: PermissionCheck, decision: str, reason: str) -> str:
        return self.repo.insert_generic(
            "policy_decisions",
            {
                "run_id": run_id,
                "policy_id": "permission",
                "policy_type": "identity",
                "subject": check.identity.agent_id or check.identity.user_id or "unknown",
                "action": check.action,
                "resource": f"{check.resource.resource_type}:{check.resource.resource_id}",
                "decision": decision,
                "reason": reason,
                "metadata": {"roles": check.identity.roles},
                "created_at": now_iso(),
            },
        )

    def can_delegate(self, coordinator_id: str, target_agent_id: str, action: str) -> bool:
        rule = self.config.delegation.get(coordinator_id)
        if not rule:
            return False
        return target_agent_id in rule.can_delegate_to and action in rule.allowed_actions
