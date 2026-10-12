from __future__ import annotations

from agentgov.storage.repositories import Repository


class DashboardService:
    def __init__(self, repo: Repository):
        self.repo = repo

    def overview(self) -> dict:
        runs = self.repo.query_all("runs")
        approvals = self.repo.query_all("approvals")
        ledger = self.repo.query_all("budget_ledger")
        messages = self.repo.query_all("agent_messages")
        policy_decisions = self.repo.query_all("policy_decisions")
        return {
            "runs": len(runs),
            "running": len([r for r in runs if r["status"] == "running"]),
            "completed": len([r for r in runs if r["status"] == "completed"]),
            "failed": len([r for r in runs if r["status"] == "failed"]),
            "rejected": len([r for r in runs if r["status"] == "rejected"]),
            "pending_approvals": len([a for a in approvals if a["status"] == "pending"]),
            "cost_usd": sum(float(x.get("amount_usd") or 0) for x in ledger if x.get("entry_type") == "settle"),
            "agent_messages": len(messages),
            "policy_decisions": len(policy_decisions),
        }

    def run_detail(self, run_id: str) -> dict:
        return {
            "run": self.repo.get_run(run_id),
            "steps": self.repo.list_steps(run_id),
            "model_calls": self.repo.query_all("model_calls", "WHERE run_id = ?", (run_id,)),
            "tool_calls": self.repo.query_all("tool_calls", "WHERE run_id = ?", (run_id,)),
            "action_intents": self.repo.query_all("action_intents", "WHERE run_id = ? ORDER BY created_at", (run_id,)),
            "observations": self.repo.query_all("observations", "WHERE run_id = ? ORDER BY created_at", (run_id,)),
            "sandbox_actions": self.repo.query_all("sandbox_actions", "WHERE run_id = ?", (run_id,)),
            "policy_decisions": self.repo.query_all("policy_decisions", "WHERE run_id = ?", (run_id,)),
            "budget_ledger": self.repo.query_all("budget_ledger", "WHERE run_id = ?", (run_id,)),
            "experience_candidates": self.repo.query_all("experience_candidates", "WHERE source_run_id = ?", (run_id,)),
            "evidence_refs": self.repo.query_all("evidence_refs", "WHERE run_id = ?", (run_id,)),
            "artifacts": self.repo.query_all("artifacts", "WHERE run_id = ?", (run_id,)),
        }

    def session_detail(self, session_id: str) -> dict:
        return {
            "session": self.repo.get_session(session_id),
            "runs": self.repo.list_runs_for_session(session_id),
            "steps": self.repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "messages": self.repo.query_all("agent_messages", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "model_calls": self.repo.query_all(
                "model_calls",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at",
                (session_id,),
            ),
            "tool_calls": self.repo.query_all(
                "tool_calls",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)",
                (session_id,),
            ),
            "action_intents": self.repo.query_all(
                "action_intents",
                "WHERE session_id = ? ORDER BY created_at",
                (session_id,),
            ),
            "observations": self.repo.query_all(
                "observations",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at",
                (session_id,),
            ),
            "evidence_refs": self.repo.query_all(
                "evidence_refs",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)",
                (session_id,),
            ),
            "budget_ledger": self.repo.query_all(
                "budget_ledger",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at",
                (session_id,),
            ),
            "artifacts": self.repo.list_artifacts_for_session(session_id),
            "matching_reports": self.repo.list_matching_reports_for_session(session_id),
            "team_snapshot": self.repo.get_team_snapshot_for_session(session_id),
        }

    def agent_detail(self, agent_id: str) -> dict:
        runs = self.repo.list_runs_for_agent(agent_id)
        return {
            "agent_id": agent_id,
            "runs": runs,
            "completed": len([r for r in runs if r["status"] == "completed"]),
            "failed": len([r for r in runs if r["status"] == "failed"]),
            "model_calls": self.repo.query_all(
                "model_calls",
                "WHERE run_id IN (SELECT id FROM runs WHERE agent_id = ?) ORDER BY created_at DESC",
                (agent_id,),
            ),
            "tool_calls": self.repo.query_all("tool_calls", "WHERE caller_agent_id = ?", (agent_id,)),
            "evidence_refs": self.repo.query_all(
                "evidence_refs",
                "WHERE run_id IN (SELECT id FROM runs WHERE agent_id = ?)",
                (agent_id,),
            ),
        }

    def queue(self) -> dict:
        return {
            "queue": self.repo.query_all("run_queue", "ORDER BY created_at DESC"),
            "leases": self.repo.query_all("run_leases", "ORDER BY created_at DESC"),
            "running_runs": self.repo.query_all("runs", "WHERE status = ? ORDER BY created_at DESC", ("running",)),
            "recent_runs": self.repo.query_all("runs", "ORDER BY created_at DESC LIMIT 20"),
        }

    def security(self) -> dict:
        return {
            "policy_decisions": self.repo.query_all("policy_decisions", "ORDER BY created_at DESC LIMIT 100"),
            "delegation_grants": self.repo.query_all("delegation_grants", "ORDER BY created_at DESC"),
            "approvals": self.repo.query_all("approvals", "ORDER BY created_at DESC"),
            "budget_ledger": self.repo.query_all("budget_ledger", "ORDER BY created_at DESC LIMIT 100"),
        }
