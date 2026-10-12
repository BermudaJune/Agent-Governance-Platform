from __future__ import annotations

from agentgov.config.schema import PolicyConfig
from agentgov.policy.context import PolicyContext
from agentgov.policy.decisions import PolicyDecisionResult


def evaluate_builtin(policy: PolicyConfig, context: PolicyContext) -> PolicyDecisionResult:
    if policy.type == "budget":
        estimated = float(context.attributes.get("estimated_cost_usd", 0))
        if policy.max_usd is not None and estimated > policy.max_usd:
            return PolicyDecisionResult("deny", policy.id, "budget", "estimated cost exceeds policy", {"estimated": estimated})
        return PolicyDecisionResult("allow", policy.id, "budget", "budget policy passed", {"estimated": estimated})
    if policy.type == "hitl":
        if context.attributes.get("requires_approval"):
            return PolicyDecisionResult("require_approval", policy.id, "hitl", "action requires human approval")
        return PolicyDecisionResult("allow", policy.id, "hitl", "approval not required")
    if policy.type == "sandbox":
        if context.attributes.get("filesystem") == "write":
            return PolicyDecisionResult("deny", policy.id, "sandbox", "write filesystem denied in MVP sandbox")
        return PolicyDecisionResult("allow", policy.id, "sandbox", "sandbox boundary passed")
    return PolicyDecisionResult("allow", policy.id, policy.type, "policy has no blocking condition")
