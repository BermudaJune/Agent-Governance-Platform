from __future__ import annotations

from collections import Counter

from agentgov.capabilities.models import TaskRequirement
from agentgov.capabilities.registry import CapabilityRegistry
from agentgov.teams.models import TeamMatchingReport


class TeamMatcher:
    def __init__(self, registry: CapabilityRegistry):
        self.registry = registry

    def match_team(
        self,
        requirement: TaskRequirement,
        agent_ids: list[str],
        *,
        team_id: str | None = None,
        use_llm: bool = False,
    ) -> TeamMatchingReport:
        unique_agents = list(dict.fromkeys(agent_ids))
        agent_caps = {agent_id: set(self.registry.agent_capability_ids(agent_id)) for agent_id in unique_agents}
        available = set().union(*agent_caps.values()) if agent_caps else set()
        required = set(requirement.required_capabilities)
        covered = sorted(required & available)
        missing = sorted(required - available)
        redundant = self._redundant_agents(agent_caps, required)
        score = 1.0 if not required else len(covered) / len(required)
        risk_items = [{"type": risk, "severity": "medium", "reason": f"Task requires {risk} capability"} for risk in requirement.risk_hints]
        token_warnings = []
        for agent_id, caps in agent_caps.items():
            if required and not caps.intersection(required) and not caps.intersection({"coordination.plan", "coordination.delegate"}):
                token_warnings.append(f"{agent_id} has no direct required capability for this task")
        token_warnings.extend([f"{agent_id} overlaps with other agents on required capabilities" for agent_id in redundant])
        decision = "proceed"
        if missing:
            decision = "adjust"
        if score < 0.4:
            decision = "block"
        if any(item["type"] in {"write", "command", "network"} for item in risk_items) and score >= 0.4:
            decision = "approval_required" if missing else "proceed"
        explanation = (
            f"Covered {len(covered)}/{len(required)} required capabilities."
            if required
            else "No explicit capabilities detected; team can proceed with coordinator judgement."
        )
        return TeamMatchingReport(
            team_id=team_id,
            score=round(score, 3),
            decision=decision,
            covered_capabilities=covered,
            missing_capabilities=missing,
            redundant_agents=redundant,
            suggested_agents=[],
            risk_items=risk_items,
            token_waste_warnings=token_warnings,
            checker="rules+llm" if use_llm else "rules",
            explanation=explanation,
        )

    def _redundant_agents(self, agent_caps: dict[str, set[str]], required: set[str]) -> list[str]:
        if not required:
            return []
        relevant_counts = Counter()
        for caps in agent_caps.values():
            relevant_counts.update(caps & required)
        redundant: list[str] = []
        for agent_id, caps in agent_caps.items():
            relevant = caps & required
            if relevant and all(relevant_counts[item] > 1 for item in relevant):
                redundant.append(agent_id)
        return redundant[1:] if len(redundant) > 1 else []
