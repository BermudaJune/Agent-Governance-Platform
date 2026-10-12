from __future__ import annotations

from agentgov.config.schema import PolicyConfig
from agentgov.policy.context import PolicyContext
from agentgov.policy.decisions import PolicyDecisionResult
from agentgov.policy.rules import evaluate_builtin
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class PolicyEngine:
    def __init__(self, repo: Repository, policies: list[PolicyConfig]):
        self.repo = repo
        self.policies = policies

    def enforce(self, context: PolicyContext) -> list[PolicyDecisionResult]:
        results = [evaluate_builtin(policy, context) for policy in self.policies]
        for result in results:
            self.repo.insert_generic(
                "policy_decisions",
                {
                    "run_id": context.run_id,
                    "policy_id": result.policy_id,
                    "policy_type": result.policy_type,
                    "subject": context.subject,
                    "action": context.action,
                    "resource": context.resource,
                    "decision": result.decision,
                    "reason": result.reason,
                    "metadata": result.metadata,
                    "created_at": now_iso(),
                },
            )
        return results

    def first_blocking(self, context: PolicyContext) -> PolicyDecisionResult | None:
        for result in self.enforce(context):
            if result.decision in {"deny", "require_approval", "pause"}:
                return result
        return None
