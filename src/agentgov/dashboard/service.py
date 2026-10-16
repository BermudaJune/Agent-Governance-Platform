from __future__ import annotations

from agentgov.storage.repositories import Repository
from agentgov.runtime.dynamic_governance import DynamicGovernanceService


class DashboardService:
    def __init__(self, repo: Repository, config_path: str | None = None):
        self.repo = repo
        self.dynamic_governance = DynamicGovernanceService(repo, config_path) if config_path else None

    def _ensure_session_agents(self, session_id: str) -> None:
        if self.dynamic_governance:
            self.dynamic_governance.ensure_root(session_id)

    def workbench(self) -> dict:
        sessions = self.repo.list_sessions()
        runs = self.repo.list_runs()
        approvals = self.repo.query_all("approvals", "ORDER BY created_at DESC")
        queue = self.queue()
        overview = self.overview()

        runs_by_session: dict[str, list[dict]] = {}
        for run in runs:
            runs_by_session.setdefault(run["session_id"], []).append(run)

        pending_approvals = [a for a in approvals if a["status"] == "pending"]
        failed_runs = [r for r in runs if r["status"] == "failed"]
        blocked_sessions = [
            s for s in sessions
            if s["status"] in {"failed", "blocked", "awaiting_approval", "needs_replan", "paused", "cancelled"}
        ]
        active_sessions = [
            self._session_summary(session, runs_by_session.get(session["id"], []))
            for session in sessions
            if session["status"] in {"running", "pending", "idle", "awaiting_approval", "needs_replan", "paused", "failed"}
        ][:12]

        attention_items = []
        for approval in pending_approvals[:6]:
            run = self.repo.get_run(approval["run_id"]) if approval.get("run_id") else None
            attention_items.append({
                "id": approval["id"],
                "kind": "approval",
                "severity": "warning",
                "title": "待审批工具调用",
                "summary": approval.get("reason") or approval.get("requested_by") or "-",
                "session_id": run.get("session_id") if run else None,
                "run_id": approval.get("run_id"),
                "action": "open_approvals",
                "created_at": approval.get("created_at"),
            })
        for run in failed_runs[:8]:
            attention_items.append({
                "id": run["id"],
                "kind": "failed_run",
                "severity": "danger",
                "title": f"{run['agent_id']} 执行失败",
                "summary": run.get("error") or run.get("input_summary") or "-",
                "session_id": run["session_id"],
                "run_id": run["id"],
                "action": "open_run",
                "created_at": run.get("created_at"),
            })
        for session in blocked_sessions[:8]:
            attention_items.append({
                "id": session["id"],
                "kind": "session_attention",
                "severity": "warning" if session["status"] in {"paused", "awaiting_approval"} else "danger",
                "title": session.get("title") or session["id"],
                "summary": f"{session['status']} / {session.get('root_agent_id') or 'no root agent'}",
                "session_id": session["id"],
                "run_id": None,
                "action": "open_session",
                "created_at": session.get("updated_at") or session.get("created_at"),
            })

        attention_items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return {
            "overview": overview,
            "attention_items": attention_items[:12],
            "active_sessions": active_sessions,
            "runtime": {
                "queue_items": len(queue["queue"]),
                "leases": len(queue["leases"]),
                "running_runs": len(queue["running_runs"]),
                "recent_runs": len(queue["recent_runs"]),
            },
            "audit_summary": {
                "pending_approvals": len(pending_approvals),
                "failed_runs": len(failed_runs),
                "blocked_sessions": len(blocked_sessions),
                "policy_decisions": overview["policy_decisions"],
                "agent_messages": overview["agent_messages"],
            },
            "backend_gaps": [
                "artifact content restore across external storage",
                "Docker or remote Worker sandbox isolation",
                "evolution candidate replay and canary release",
                "MCP registry import and health checks",
            ],
        }

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
            "artifact_versions": self.repo.query_all("artifact_versions", "WHERE run_id = ? ORDER BY created_at", (run_id,)),
            "knowledge_grants": self.repo.list_knowledge_grants_for_run(run_id),
            "knowledge_access_events": self.repo.query_all("knowledge_access_events", "WHERE run_id = ? ORDER BY created_at", (run_id,)),
        }

    def session_detail(self, session_id: str) -> dict:
        self._ensure_session_agents(session_id)
        return {
            "session": self.repo.get_session(session_id),
            "runs": self.repo.list_runs_for_session(session_id),
            "approvals": self.repo.query_all(
                "approvals",
                "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at DESC",
                (session_id,),
            ),
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
            "artifact_versions": self.repo.list_artifact_versions(session_id),
            "matching_reports": self.repo.list_matching_reports_for_session(session_id),
            "team_snapshot": self.repo.get_team_snapshot_for_session(session_id),
            "plans": self.repo.list_plans_for_session(session_id),
            "task_nodes": self.repo.list_task_nodes_for_session(session_id),
            "task_edges": self.repo.list_task_edges_for_session(session_id),
            "knowledge_sources": self.repo.list_session_knowledge(session_id),
            "knowledge_grants": self.repo.list_knowledge_grants(session_id),
            "knowledge_access_events": self.repo.query_all("knowledge_access_events", "WHERE session_id = ? ORDER BY created_at", (session_id,)),
            "knowledge_policy": (self.repo.get_session(session_id) or {}).get("metadata", {}).get("knowledge_policy", {}),
            "session_agents": self.repo.list_session_agents(session_id),
            "delegation_requests": self.repo.list_delegation_requests(session_id),
            "skill_grants": self.repo.list_session_skill_grants(session_id),
            "tool_grants": self.repo.list_session_tool_grants(session_id),
            "agent_lifecycle_events": self.repo.list_agent_lifecycle_events(session_id),
            "checkpoints": self.repo.list_checkpoints(session_id),
            "rollback_events": self.repo.list_rollback_events(session_id),
            "requirements": self.repo.list_requirements_for_session(session_id),
            "current_requirement": self.repo.get_current_requirement(session_id),
            "feedback": self.repo.list_session_feedback(session_id),
            "replan_required": (self.repo.get_session(session_id) or {}).get("status") == "needs_replan",
            "affected_nodes": [
                node for node in self.repo.list_task_nodes_for_session(session_id)
                if node.get("status") in {"needs_replan", "stale"}
            ],
            "stale_artifacts": [
                artifact for artifact in self.repo.list_artifacts_for_session(session_id)
                if (artifact.get("metadata") or {}).get("stale")
            ],
        }

    def session_audit_report(self, session_id: str) -> dict:
        self._ensure_session_agents(session_id)
        session = self.repo.get_session(session_id)
        runs = self.repo.list_runs_for_session(session_id)
        run_ids = [run["id"] for run in runs]
        steps = self.repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,))
        approvals = self.repo.query_all(
            "approvals",
            "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at",
            (session_id,),
        )
        policy_decisions = self.repo.query_all(
            "policy_decisions",
            "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at",
            (session_id,),
        )
        tool_calls = self.repo.query_all(
            "tool_calls",
            "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)",
            (session_id,),
        )
        model_calls = self.repo.query_all(
            "model_calls",
            "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY created_at",
            (session_id,),
        )
        artifacts = self.repo.list_artifacts_for_session(session_id)
        rollback_events = [
            step for step in steps
            if any(token in step["event_type"] for token in ("rollback", "retry", "restore"))
        ]
        knowledge_events = self.repo.query_all("knowledge_access_events", "WHERE session_id = ? ORDER BY created_at", (session_id,))
        session_agents = self.repo.list_session_agents(session_id)
        delegation_requests = self.repo.list_delegation_requests(session_id)
        lifecycle_events = self.repo.list_agent_lifecycle_events(session_id)
        return {
            "session": session,
            "summary": {
                "runs": len(runs),
                "events": len(steps),
                "approvals": len(approvals),
                "policy_decisions": len(policy_decisions),
                "tool_calls": len(tool_calls),
                "model_calls": len(model_calls),
                "artifacts": len(artifacts),
                "rollback_events": len(rollback_events),
                "knowledge_sources": len(self.repo.list_session_knowledge(session_id)),
                "knowledge_accesses": len(knowledge_events),
                "session_agents": len(session_agents),
                "delegation_requests": len(delegation_requests),
            },
            "timeline": steps,
            "decision_chain": policy_decisions + approvals,
            "tool_chain": tool_calls,
            "model_chain": model_calls,
            "artifact_chain": artifacts,
            "rollback_chain": rollback_events,
            "responsibility_chain": [
                {
                    "run_id": run["id"],
                    "agent_id": run["agent_id"],
                    "status": run["status"],
                    "input_summary": run.get("input_summary"),
                    "error": run.get("error"),
                }
                for run in runs
                if run["id"] in run_ids
            ],
            "knowledge_chain": knowledge_events,
            "delegation_chain": delegation_requests,
            "agent_lifecycle_chain": lifecycle_events,
            "grant_chain": self.repo.list_session_skill_grants(session_id) + self.repo.list_session_tool_grants(session_id),
            "checkpoints": self.repo.list_checkpoints(session_id),
            "rollback_events": self.repo.list_rollback_events(session_id),
        }

    def session_available_actions(self, session_id: str) -> dict:
        session = self.repo.get_session(session_id)
        runs = self.repo.list_runs_for_session(session_id)
        if not session:
            return {"session_id": session_id, "actions": []}
        nodes = self.repo.list_task_nodes_for_session(session_id)
        if nodes:
            current_run_ids = {node["run_id"] for node in nodes if node.get("status") != "superseded"}
            runs = [run for run in runs if run["id"] in current_run_ids]
        else:
            runs = [run for run in runs if run.get("run_type") != "leader_planning"]
        terminal = {"completed", "failed", "rejected", "cancelled", "timeout"}
        has_pending = any(run["status"] in {"pending", "queued", "blocked"} for run in runs)
        has_running = any(run["status"] == "running" for run in runs)
        has_paused = any(run["status"] == "paused" for run in runs) or session["status"] == "paused"
        plan = self.repo.get_plan_for_session(session_id) or {}
        plan_blocked = session["status"] in {"needs_replan", "awaiting_approval", "paused", "cancelled"} or plan.get("status") in {"needs_replan", "awaiting_approval", "rejected"}
        return {
            "session_id": session_id,
            "status": session["status"],
            "actions": [
                self._action("execute-pending", "执行待处理", has_pending and not plan_blocked, "请先完成重规划、审批或恢复" if plan_blocked else "没有待处理 Run", f"/sessions/{session_id}/execute-pending"),
                self._action("pause", "暂停", has_running or session["status"] in {"running", "pending"}, "没有运行中的 Run", f"/sessions/{session_id}/pause"),
                self._action("resume", "恢复", has_paused, "Session 未暂停", f"/sessions/{session_id}/resume"),
                self._action("cancel", "取消", session["status"] not in terminal, "Session 已终止", f"/sessions/{session_id}/cancel"),
                self._action("rollback", "回滚到检查点", bool(self.repo.list_checkpoints(session_id)), "暂无可用检查点", f"/sessions/{session_id}/rollback"),
            ],
        }

    def run_available_actions(self, run_id: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            return {"run_id": run_id, "actions": []}
        terminal = {"completed", "failed", "rejected", "cancelled", "timeout"}
        return {
            "run_id": run_id,
            "status": run["status"],
            "actions": [
                self._action("execute", "执行", run["status"] == "pending", "Run 不在 pending 状态", f"/runs/{run_id}/execute"),
                self._action("pause", "暂停", run["status"] not in terminal | {"paused"}, "Run 已暂停或终止", f"/runs/{run_id}/pause"),
                self._action("resume", "恢复", run["status"] == "paused", "Run 未暂停", f"/runs/{run_id}/resume"),
                self._action("cancel", "取消", run["status"] not in terminal, "Run 已终止", f"/runs/{run_id}/cancel"),
                self._action("retry", "重试", run["status"] in {"failed", "cancelled", "timeout", "rejected"}, "只有失败或取消的 Run 可以重试", f"/runs/{run_id}/retry"),
            ],
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

    def _session_summary(self, session: dict, runs: list[dict]) -> dict:
        return {
            "id": session["id"],
            "title": session.get("title"),
            "status": session["status"],
            "root_agent_id": session.get("root_agent_id"),
            "team_id": session.get("team_id"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "stage": self._stage_for_session(session["status"], runs),
            "run_counts": {
                "total": len(runs),
                "running": len([run for run in runs if run["status"] == "running"]),
                "pending": len([run for run in runs if run["status"] in {"pending", "queued", "blocked"}]),
                "failed": len([run for run in runs if run["status"] == "failed"]),
                "completed": len([run for run in runs if run["status"] == "completed"]),
            },
        }

    def _stage_for_session(self, status: str, runs: list[dict]) -> str:
        if status in {"failed", "cancelled", "blocked"} or any(run["status"] == "failed" for run in runs):
            return "needs_intervention"
        if status == "awaiting_approval":
            return "approval"
        if status == "completed":
            return "review"
        if any(run["status"] == "running" for run in runs):
            return "executing"
        if runs:
            return "planned"
        return "draft"

    def _action(self, action_id: str, label: str, enabled: bool, disabled_reason: str, endpoint: str) -> dict:
        return {
            "id": action_id,
            "label": label,
            "enabled": enabled,
            "disabled_reason": "" if enabled else disabled_reason,
            "method": "POST",
            "endpoint": endpoint,
        }
