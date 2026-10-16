from __future__ import annotations

from pathlib import Path
from threading import Lock

from agentgov.event_stream.stream import EventStream
from agentgov.memory.cases import SessionCaseService
from agentgov.planning.planner import RuleBasedSessionPlanner
from agentgov.planning.models import TaskNodeSpec
from agentgov.planning.service import PlanningService
from agentgov.runtime.agent_loop import AgentLoop
from agentgov.runtime.state_machine import ensure_transition
from agentgov.scheduler.queue import RunQueue
from agentgov.storage.models import RunRecord, SessionRecord, now_iso, new_id
from agentgov.storage.repositories import Repository


class RunService:
    def __init__(
        self,
        repo: Repository,
        events: EventStream,
        loop: AgentLoop,
        queue: RunQueue | None = None,
        planner: RuleBasedSessionPlanner | None = None,
    ):
        self.repo = repo
        self.events = events
        self.loop = loop
        self.queue = queue
        self.planner = planner or RuleBasedSessionPlanner()
        self.planning = PlanningService(repo, events, queue)
        self.leader_workflow = None
        self._execution_locks = {}
        self._execution_guard = Lock()
        self._plan_decision_lock = Lock()

    def create_session(
        self,
        title: str,
        owner_id: str,
        root_agent_id: str | None = None,
        team_id: str | None = None,
        knowledge_sources: list[dict] | None = None,
        knowledge_policy: dict | None = None,
        objective: str | None = None,
        requirement_contract: dict | None = None,
    ) -> SessionRecord:
        session = self.repo.create_session(
            SessionRecord(
                title=title,
                owner_id=owner_id,
                root_agent_id=root_agent_id,
                team_id=team_id,
                metadata={
                    "knowledge_policy": knowledge_policy or {},
                    "case_recall": SessionCaseService(self.repo).recall(owner_id, objective or title),
                },
            )
        )
        for source in knowledge_sources or []:
            self.repo.add_session_knowledge(session.id, source)
        if objective:
            self.repo.create_requirement_version(
                session.id,
                objective,
                requirement_contract or {"objective": objective},
                source="user",
                change_reason="initial task submission",
                created_by=owner_id,
            )
        return session

    def submit_session_feedback(
        self,
        session_id: str,
        *,
        target_type: str,
        target_id: str | None,
        message: str,
        requested_action: str = "replan",
        created_by: str = "operator",
        reason_type: str = "unspecified",
    ) -> dict:
        session = self.repo.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        message = message.strip()
        if not message:
            raise ValueError("feedback message must not be empty")
        if target_type not in {"session", "requirement", "action", "artifact", "agent"}:
            raise ValueError("unsupported feedback target type")
        if requested_action not in {"replan", "record"}:
            raise ValueError("unsupported feedback action")
        if reason_type not in {"unspecified", "new_requirement", "misunderstanding", "execution_issue", "preference"}:
            raise ValueError("unsupported feedback reason")
        if target_type not in {"session", "requirement"}:
            if not target_id:
                raise ValueError("a feedback target must be selected")
            targets = {
                "action": {node["id"] for node in self.repo.list_task_nodes_for_session(session_id) if node["status"] != "superseded"},
                "artifact": {artifact["id"] for artifact in self.repo.list_artifacts_for_session(session_id)},
                "agent": {agent["agent_id"] for agent in self.repo.list_session_agents(session_id)},
            }
            if target_id not in targets[target_type]:
                raise ValueError("feedback target does not belong to the current session")
        current = self.repo.get_current_requirement(session_id)
        objective = (current or {}).get("objective") or session.get("context_summary") or session.get("title", "")
        contract = dict((current or {}).get("contract") or {})
        contract["latest_feedback"] = message
        contract["feedback_target"] = {"type": target_type, "id": target_id}
        contract["corrections"] = [*(contract.get("corrections") or []), {"message": message, "target_type": target_type, "target_id": target_id, "reason_type": reason_type}]
        impact = self.analyze_feedback_impact(session_id, target_type, target_id)
        requirement = self.repo.create_requirement_version(
            session_id,
            objective,
            contract,
            source="user_correction",
            parent_id=(current or {}).get("id"),
            change_reason=message,
            created_by=created_by,
        )
        plan = self.repo.get_plan_for_session(session_id)
        feedback = self.repo.create_session_feedback(
            {
                "session_id": session_id,
                "target_type": target_type,
                "target_id": target_id,
                "message": message,
                "reason_type": reason_type,
                "requested_action": requested_action,
                "impact": impact,
                "status": "needs_replan" if requested_action == "replan" else "recorded",
                "requirement_id": requirement["id"],
                "plan_id": plan.get("id") if plan else None,
                "created_by": created_by,
            }
        )
        if requested_action == "record":
            return {"feedback": feedback, "requirement": requirement, "impact": impact, "status": "recorded"}
        for node_id in impact["affected_node_ids"]:
            node = next((item for item in self.repo.list_task_nodes_for_session(session_id) if item["id"] == node_id), None)
            if node and node.get("status") not in {"completed", "failed", "cancelled"}:
                self.repo.update_generic("task_nodes", node_id, {"status": "needs_replan", "updated_at": now_iso()})
            elif node:
                self.repo.update_generic("task_nodes", node_id, {"status": "stale", "updated_at": now_iso()})
        for artifact in impact["stale_artifacts"]:
            self.repo.update_generic("artifacts", artifact["id"], {"metadata": {**(artifact.get("metadata") or {}), "stale": True, "stale_reason": message}})
            for version in self.repo.query_all("artifact_versions", "WHERE artifact_id = ?", (artifact["id"],)):
                self.repo.update_generic("artifact_versions", version["id"], {"status": "stale"})
        if plan:
            self.repo.update_generic("session_plans", plan["id"], {"status": "needs_replan", "approval_status": "required", "updated_at": now_iso()})
        for request in self.repo.list_delegation_requests(session_id):
            if request["status"] == "pending":
                self.repo.update_generic("delegation_requests", request["id"], {"status": "superseded", "decided_at": now_iso()})
                if request.get("approval_id"):
                    self.repo.update_generic("approvals", request["approval_id"], {"status": "superseded", "reason": "需求发生变更，等待新计划", "decided_at": now_iso()})
        affected_runs = {node.get("run_id") for node in self.repo.list_task_nodes_for_session(session_id) if node["id"] in impact["affected_node_ids"]}
        for approval in self.repo.query_all("approvals", "WHERE status = 'pending'"):
            if approval.get("run_id") in affected_runs:
                self.repo.update_generic("approvals", approval["id"], {"status": "superseded", "reason": "任务分支已被用户校正", "decided_at": now_iso()})
        self.repo.update_session_status(session_id, "needs_replan", f"User correction requires Leader replan: {message}")
        run_id = next((run["id"] for run in reversed(self.repo.list_runs_for_session(session_id))), None)
        if run_id:
            self.events.append(
                run_id,
                session_id,
                "session.feedback.submitted",
                "operator",
                created_by,
                "needs_replan",
                {"feedback_id": feedback["id"], "requirement_id": requirement["id"], "impact": impact},
            )
        return {"feedback": feedback, "requirement": requirement, "impact": impact, "status": "needs_replan"}

    def analyze_feedback_impact(self, session_id: str, target_type: str, target_id: str | None) -> dict:
        nodes = [node for node in self.repo.list_task_nodes_for_session(session_id) if node["status"] != "superseded"]
        affected: set[str] = set()
        if target_type in {"session", "requirement"} or not target_id:
            affected.update(node["id"] for node in nodes)
        elif target_type == "action":
            affected.update(node["id"] for node in nodes if node["id"] == target_id or node.get("node_key") == target_id)
        elif target_type == "agent":
            affected.update(node["id"] for node in nodes if node.get("assigned_agent_id") == target_id)
        elif target_type == "artifact":
            artifacts = self.repo.list_artifacts_for_session(session_id)
            matching = [item for item in artifacts if item["id"] == target_id or item.get("path") == target_id]
            affected.update(node["id"] for node in nodes if any(item.get("run_id") == node.get("run_id") for item in matching))
        affected = self._include_downstream_nodes(nodes, affected)
        stale_artifacts = [
            item for item in self.repo.list_artifacts_for_session(session_id)
            if item.get("run_id") in {node.get("run_id") for node in nodes if node["id"] in affected}
        ]
        preserved = [node["id"] for node in nodes if node["id"] not in affected and node.get("status") == "completed"]
        return {
            "target": {"type": target_type, "id": target_id},
            "affected_node_ids": sorted(affected),
            "affected_node_keys": [node["node_key"] for node in nodes if node["id"] in affected],
            "preserved_node_ids": preserved,
            "stale_artifacts": stale_artifacts,
            "approval_required": True,
            "replan_scope": "affected_branch" if affected and len(affected) < len(nodes) else "session",
        }

    def replan_session(self, session_id: str, *, actor_id: str = "leader") -> dict:
        if self.leader_workflow and self.leader_workflow.is_managed(session_id):
            return self.leader_workflow.plan(session_id)
        session = self.repo.get_session(session_id)
        current = self.repo.get_current_requirement(session_id)
        previous_plan = self.repo.get_plan_for_session(session_id)
        if not session or not current:
            raise KeyError(session_id)
        if previous_plan and previous_plan.get("status") not in {"needs_replan", "replanning", "failed", "rejected"}:
            return {"status": "no_replan_required", "session_id": session_id, "plan": previous_plan}
        nodes = [node for node in self.repo.list_task_nodes_for_session(session_id) if node["status"] != "superseded"]
        affected = [node for node in nodes if node.get("status") in {"needs_replan", "stale"}]
        if not affected:
            return {"status": "no_affected_nodes", "session_id": session_id, "plan": previous_plan}
        feedback = [item for item in self.repo.list_session_feedback(session_id) if item.get("status") == "needs_replan"]
        feedback_text = "\n".join(item.get("message", "") for item in feedback) or (previous_plan or {}).get("change_reason", "")
        affected_ids = {node["id"] for node in affected}
        specs: list[TaskNodeSpec] = []
        run_ids_by_key: dict[str, str] = {}
        node_key_by_old_id: dict[str, str] = {}
        leader = session.get("root_agent_id") or (previous_plan or {}).get("planner_agent_id") or actor_id
        for node in affected:
            node_key = f"replan_v{int(current.get('version', 1))}_{node['node_key']}"
            node_key_by_old_id[node["id"]] = node_key
            dependency_keys: list[str] = []
            for edge in self.repo.query_all("task_edges", "WHERE target_node_id = ?", (node["id"],)):
                if edge["source_node_id"] in affected_ids:
                    source = next((item for item in affected if item["id"] == edge["source_node_id"]), None)
                    if source:
                        dependency_keys.append(node_key_by_old_id.get(source["id"], f"replan_v{int(current.get('version', 1))}_{source['node_key']}"))
            instruction = node["instruction"]
            if feedback_text:
                instruction = f"{instruction}\n\n用户校正（必须纳入本次执行）：{feedback_text}"
            specs.append(
                TaskNodeSpec(
                    node_key=node_key,
                    assigned_agent_id=node["assigned_agent_id"],
                    title=f"重规划：{node['title']}",
                    instruction=instruction,
                    node_type=node.get("node_type", "agent_task"),
                    required_capabilities=node.get("required_capabilities", []),
                    required_tools=node.get("required_tools", []),
                    input_refs=[*node.get("input_refs", []), *(f"previous_node:{ref}" for ref in node.get("input_refs", []))],
                    output_contract=node.get("output_contract", {}),
                    depends_on=dependency_keys,
                )
            )
        for spec in specs:
            parent_run_id = None
            old_node = next((item for item in affected if node_key_by_old_id.get(item["id"]) == spec.node_key), None)
            if old_node:
                parent_run_id = old_node.get("run_id")
            run = self.create_run(session_id, spec.assigned_agent_id, spec.instruction, parent_run_id=parent_run_id)
            run_ids_by_key[spec.node_key] = run.id
        plan_bundle = self.planning.create_plan(
            session_id=session_id,
            objective=current["objective"],
            strategy=(previous_plan or {}).get("strategy", "leader_worker"),
            planner_agent_id=leader,
            nodes=specs,
            run_ids_by_node_key=run_ids_by_key,
            requirement_id=current["id"],
            parent_plan_id=(previous_plan or {}).get("id"),
            change_reason=feedback_text or "user requested replan",
            approval_status="pending",
        )
        new_plan_id = plan_bundle["plans"][-1]["id"]
        new_nodes = {node["node_key"]: node for node in self.repo.list_task_nodes_for_plan(new_plan_id)}
        # Keep edges to unchanged upstream work so its evidence remains available.
        for old_node in affected:
            replacement = new_nodes[node_key_by_old_id[old_node["id"]]]
            for edge in self.repo.query_all("task_edges", "WHERE target_node_id = ?", (old_node["id"],)):
                if edge["source_node_id"] not in affected_ids:
                    self.repo.insert_generic("task_edges", {
                        "plan_id": new_plan_id,
                        "source_node_id": edge["source_node_id"],
                        "target_node_id": replacement["id"],
                        "edge_type": "depends_on",
                        "payload_key": edge.get("payload_key"),
                        "created_at": now_iso(),
                    })
            self.repo.update_generic("task_nodes", old_node["id"], {"status": "superseded", "updated_at": now_iso()})
        for item in feedback:
            self.repo.update_generic("session_feedback", item["id"], {"status": "planned"})
        self.repo.update_generic("session_plans", new_plan_id, {"status": "awaiting_approval", "approval_status": "required", "updated_at": now_iso()})
        if previous_plan:
            self.repo.update_generic("session_plans", previous_plan["id"], {"status": "superseded", "updated_at": now_iso()})
        self.repo.update_session_status(session_id, "awaiting_approval", "New Leader plan is ready for human approval")
        for spec in specs:
            run_id = run_ids_by_key[spec.node_key]
            self.repo.insert_generic(
                "agent_messages",
                {
                    "trace_id": run_id,
                    "session_id": session_id,
                    "parent_run_id": None,
                    "source_agent_id": leader,
                    "target_agent_id": spec.assigned_agent_id,
                    "message_type": "plan.replanned",
                    "payload": {"requirement_id": current["id"], "node_key": spec.node_key, "change_reason": feedback_text},
                    "status": "sent",
                    "created_at": now_iso(),
                },
            )
        event_run = run_ids_by_key[specs[0].node_key]
        self.events.append(
            event_run,
            session_id,
            "session.plan.replanned",
            "leader",
            leader,
            "awaiting_approval",
            {"requirement_id": current["id"], "parent_plan_id": (previous_plan or {}).get("id"), "plan_id": new_plan_id},
        )
        return {"status": "awaiting_approval", "session_id": session_id, "plan": self.planning.get_plan_bundle(session_id), "reused_node_ids": [node["id"] for node in nodes if node not in affected]}

    def decide_session_plan(self, session_id: str, approved: bool, approver_id: str, reason: str, plan_id: str | None = None) -> dict:
        lock = self.leader_workflow._lock(session_id) if self.leader_workflow and self.leader_workflow.is_managed(session_id) else self._plan_decision_lock
        with lock:
            return self._decide_session_plan(session_id, approved, approver_id, reason, plan_id)

    def _decide_session_plan(self, session_id: str, approved: bool, approver_id: str, reason: str, plan_id: str | None) -> dict:
        plan = self.repo.get_plan_for_session(session_id)
        if plan_id and (not plan or plan["id"] != plan_id):
            raise ValueError("计划已更新，请检查最新差异后再审批")
        status = "approved" if approved else "rejected"
        if plan and plan["status"] != "awaiting_approval" and plan.get("approval_status") == status:
            return {"status": status, "session_id": session_id, "plan": plan, "already_decided": True}
        if not plan or plan["status"] != "awaiting_approval":
            raise ValueError("session has no plan waiting for approval")
        if approved and self.leader_workflow and self.leader_workflow.is_managed(session_id):
            state = self.leader_workflow.state(session_id)
            if state.get("questions") or state.get("unresolved_gaps"):
                raise ValueError("请先补充必要信息或解决能力缺口，再批准执行")
        self.repo.update_generic("session_plans", plan["id"], {
            "status": "active" if approved else "rejected",
            "approval_status": status,
            "updated_at": now_iso(),
        })
        nodes = self.repo.list_task_nodes_for_plan(plan["id"])
        if not approved:
            for node in nodes:
                self.repo.update_generic("task_nodes", node["id"], {"status": "needs_replan", "updated_at": now_iso()})
        self.repo.update_session_status(session_id, "pending" if approved else "needs_replan", reason or f"plan {status}")
        if self.leader_workflow and self.leader_workflow.is_managed(session_id):
            self.leader_workflow._state(session_id, status="ready" if approved else "needs_replan")
        run_id = next((node["run_id"] for node in nodes if node.get("run_id")), None)
        if run_id:
            self.events.append(run_id, session_id, "session.plan.decided", "operator", approver_id, status, {
                "plan_id": plan["id"], "requirement_id": plan.get("requirement_id"), "approved": approved, "reason": reason,
            })
        return {"status": status, "session_id": session_id, "plan": self.repo.get_plan_for_session(session_id)}

    def _include_downstream_nodes(self, nodes: list[dict], affected: set[str]) -> set[str]:
        current_ids = {node["id"] for node in nodes}
        changed = True
        while changed:
            changed = False
            for edge in self.repo.query_all("task_edges", "WHERE source_node_id IN ({})".format(",".join("?" * len(affected)) if affected else "NULL"), tuple(affected)) if affected else []:
                if edge["target_node_id"] in current_ids and edge["target_node_id"] not in affected:
                    affected.add(edge["target_node_id"])
                    changed = True
        return affected

    def create_run(self, session_id: str, agent_id: str, input_summary: str, parent_run_id: str | None = None) -> RunRecord:
        run = self.repo.create_run(RunRecord(session_id=session_id, agent_id=agent_id, parent_run_id=parent_run_id, input_summary=input_summary))
        self.events.append(run.id, session_id, "run.started", "agent", agent_id, "started", {"input": input_summary})
        session = self.repo.get_session(session_id) or {}
        recalled = session.get("metadata", {}).get("case_recall", [])
        if recalled and agent_id == session.get("root_agent_id"):
            self.events.append(run.id, session_id, "session.cases.pinned", "system", agent_id, "completed", {
                "case_ids": [case["case_id"] for case in recalled], "reference_type": "historical_method",
            })
        return run

    def _ensure_session_agents(self, session_id: str, leader: str, members: list[str]) -> None:
        existing = {item["agent_id"] for item in self.repo.list_session_agents(session_id)}
        configured = getattr(self.planner, "_agents", {})
        for agent_id in dict.fromkeys([leader, *members]):
            if agent_id in existing:
                continue
            spec = configured.get(agent_id)
            snapshot = spec.model_dump() if spec is not None else {"id": agent_id}
            role = "leader" if agent_id == leader else "specialist"
            self.repo.insert_generic(
                "session_agents",
                {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "parent_agent_id": None if agent_id == leader else leader,
                    "role": role,
                    "origin": "reused",
                    "depth": 0 if agent_id == leader else 1,
                    "status": "active",
                    "spec_snapshot": snapshot,
                    "created_by": leader,
                    "created_at": now_iso(),
                },
            )
            self.repo.insert_generic(
                "agent_lifecycle_events",
                {
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "event_type": "agent.attached",
                    "actor_id": leader,
                    "payload": {"origin": "planned_member", "role": role},
                    "created_at": now_iso(),
                },
            )

    def grant_direct_session_knowledge(self, session_id: str, run_id: str, agent_id: str) -> None:
        sources = self.repo.list_session_knowledge(session_id)
        if not sources:
            return
        plan = self.repo.get_plan_for_session(session_id)
        self.repo.insert_generic(
            "knowledge_access_grants",
            {
                "session_id": session_id,
                "plan_id": plan["id"] if plan else None,
                "task_node_id": None,
                "run_id": run_id,
                "agent_id": agent_id,
                "source_ids": [source["id"] for source in sources if source.get("status") == "active"],
                "access_mode": "read",
                "granted_by": "operator",
                "rationale": "单 Agent Session 的直接知识范围",
                "status": "planned",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )

    def enqueue_run(self, run_id: str, priority: int = 100) -> dict:
        if self.queue is None:
            return {"status": "unavailable", "reason": "queue is not configured"}
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        queue_id = self.queue.enqueue(run_id, run["session_id"], priority)
        self.events.append(run_id, run["session_id"], "queue.item.created", "system", "run_queue", "queued", {"queue_id": queue_id})
        return {"status": "queued", "queue_id": queue_id, "run_id": run_id}

    def enqueue_session_ready_runs(self, session_id: str, priority: int = 100) -> list[dict]:
        planned = self.planning.enqueue_ready_nodes_for_session(session_id, priority)
        if planned:
            return planned
        queued: list[dict] = []
        for run in self.repo.list_runs_for_session(session_id):
            if run["status"] == "pending":
                queued.append(self.enqueue_run(run["id"], priority))
        return queued

    def execute(self, run_id: str) -> dict:
        with self._execution_guard:
            lock = self._execution_locks.setdefault(run_id, Lock())
        if not lock.acquire(blocking=False):
            return {"status": "running", "run_id": run_id, "reason": "该 Run 已在执行"}
        try:
            return self._execute(run_id)
        finally:
            lock.release()

    def _execute(self, run_id: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {
                "status": run["status"],
                "response": run.get("output_summary") or "",
                "error": run.get("error"),
                "already_terminal": True,
            }
        if run["status"] == "paused":
            return {"status": "paused", "response": run.get("output_summary") or "", "error": "run is paused"}
        if self.leader_workflow and self.leader_workflow.is_managed(run["session_id"]):
            reason = self.leader_workflow.readiness(run["session_id"], self.repo.get_task_node_for_run(run_id))
            if reason:
                return {"status": "blocked", "run_id": run_id, "reason": reason}
        planning_gate = self.planning.before_run_execute(run_id)
        if planning_gate.get("status") == "blocked":
            dependencies = [
                {"node_key": item["node_key"], "status": item["status"], "run_id": item.get("run_id")}
                for item in planning_gate.get("dependencies", [])
            ]
            self.events.append(
                run_id,
                run["session_id"],
                "task_node.blocked",
                "planner",
                "planning_service",
                "blocked",
                {"reason": planning_gate.get("reason"), "dependencies": dependencies},
            )
            return {"status": "blocked", "response": "", "error": planning_gate.get("reason"), "dependencies": dependencies}
        ensure_transition(run["status"], "running")
        self.repo.update_run_status(run_id, "running")
        self.events.append(run_id, run["session_id"], "run.status_changed", "system", "run_service", "completed", {"from": run["status"], "to": "running"})
        prompt = run["input_summary"]
        if planning_gate.get("prompt_prefix"):
            prompt = f"{planning_gate['prompt_prefix']}\n\nCurrent task:\n{run['input_summary']}"
        try:
            result = self.loop.run_once(run_id, run["session_id"], run["agent_id"], prompt)
        except Exception as exc:
            message = str(exc)
            self.repo.update_run_status(run_id, "failed", error=message)
            self.repo.update_session_status(run["session_id"], "failed", message)
            self.planning.after_run_execute(run_id, "failed", {"error": message})
            self.events.append(
                run_id,
                run["session_id"],
                "run.failed",
                "system",
                "run_service",
                "failed",
                {"status": "failed", "error": message},
            )
            return {"status": "failed", "response": "", "error": message}
        latest = self.repo.get_run(run_id)
        current_node = self.repo.get_task_node_for_run(run_id)
        current_session = self.repo.get_session(run["session_id"]) or {}
        if (current_node and current_node["status"] in {"needs_replan", "stale", "superseded"}) or current_session.get("status") in {"needs_replan", "replanning", "cancelled", "paused"}:
            status = "cancelled" if current_session.get("status") == "cancelled" else "paused"
            self.repo.update_run_status(run_id, status, output_summary=result.get("response", ""))
            self.events.append(run_id, run["session_id"], "run.result.deferred", "system", "run_service", status, {"reason": "用户已中断或校正，结果保留但不推进旧计划"})
            return {"status": status, "response": result.get("response", "")}
        if current_node and not result.get("requires_approval") and result.get("status") != "failed":
            expected = current_node.get("output_contract", {}).get("files", [])
            if isinstance(expected, list) and expected:
                workspace = (self.loop.tool_gateway.registry.repo_tools.root / "data" / "workspaces" / run["session_id"]).resolve()
                missing = []
                recorded = {Path(a["path"]).resolve() for a in self.repo.list_artifacts_for_session(run["session_id"]) if a.get("run_id") == run_id}
                for name in expected:
                    target = (workspace / str(name)).resolve()
                    if workspace not in target.parents or not target.is_file() or target not in recorded:
                        missing.append(str(name))
                if missing:
                    result = {**result, "status": "failed", "error": "缺少真实产物：" + ", ".join(missing)}
        if result.get("status") == "failed":
            message = result.get("error") or "Agent 未能完成任务，请检查工具结果或调整方案"
            self.repo.update_run_status(run_id, "failed", error=message)
            self.repo.update_session_status(run["session_id"], "failed", message)
            self.planning.after_run_execute(run_id, "failed", result)
            self.events.append(run_id, run["session_id"], "run.failed", "system", "run_service", "failed", {"error": message})
            return result
        if result.get("requires_approval"):
            self.repo.update_run_status(run_id, "paused", output_summary=result.get("response", ""), error="waiting for tool approval")
            self.planning.after_run_execute(run_id, "paused", result)
            self.events.append(
                run_id,
                run["session_id"],
                "run.awaiting_approval",
                "system",
                "run_service",
                "paused",
                {"status": "paused", "result": result},
            )
            return {"status": "paused", **result}
        if latest and latest["status"] in {"paused", "cancelled"}:
            self.planning.after_run_execute(run_id, latest["status"], result)
            self.events.append(
                run_id,
                run["session_id"],
                "run.execution_deferred",
                "system",
                "run_service",
                latest["status"],
                {"status": latest["status"], "reason": "operator changed run state during execution"},
            )
            return {"status": latest["status"], "response": result.get("response", ""), "error": latest.get("error")}
        self.repo.update_run_status(run_id, "completed", output_summary=result["response"])
        self._record_child_result_message(run_id, result)
        ready_nodes = self.planning.after_run_execute(run_id, "completed", result)
        self._finalize_session_after_run(run["session_id"])
        self.events.append(
            run_id,
            run["session_id"],
            "run.final",
            "system",
            "run_service",
            "completed",
            {"status": "completed", "result": result, "ready_downstream": ready_nodes},
        )
        return {"status": "completed", **result, "ready_downstream": ready_nodes}

    def pause_run(self, run_id: str, reason: str = "operator requested pause") -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {"status": run["status"], "already_terminal": True}
        ensure_transition(run["status"], "paused")
        self.repo.update_run_status(run_id, "paused")
        self.events.append(run_id, run["session_id"], "run.paused", "operator", "operator", "paused", {"reason": reason})
        return {"status": "paused", "run_id": run_id}

    def cancel_run(self, run_id: str, reason: str = "operator cancelled run") -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {"status": run["status"], "already_terminal": True}
        ensure_transition(run["status"], "cancelled")
        self.repo.update_run_status(run_id, "cancelled", error=reason)
        self.events.append(run_id, run["session_id"], "run.cancelled", "operator", "operator", "cancelled", {"reason": reason})
        return {"status": "cancelled", "run_id": run_id}

    def resume_run(self, run_id: str, execute_now: bool = False) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] != "paused":
            return {"status": run["status"], "run_id": run_id, "unchanged": True}
        ensure_transition(run["status"], "pending")
        self.repo.update_run_status(run_id, "pending")
        self.events.append(run_id, run["session_id"], "run.resumed", "operator", "operator", "pending", {"execute_now": execute_now})
        if execute_now:
            return self.execute(run_id)
        return {"status": "pending", "run_id": run_id}

    def retry_run(self, run_id: str, execute_now: bool = False) -> dict:
        source = self.repo.get_run(run_id)
        if not source:
            raise KeyError(run_id)
        if source["status"] not in {"failed", "cancelled", "timeout", "rejected"}:
            return {"status": source["status"], "run_id": run_id, "unchanged": True, "reason": "only terminal failures can be retried"}
        retry = self.create_run(
            source["session_id"],
            source["agent_id"],
            source["input_summary"],
            parent_run_id=source.get("parent_run_id"),
        )
        self.repo.update_generic("runs", retry.id, {"metadata": {"retry_of": run_id, "attempt": self._retry_attempt(source)}})
        node = self.repo.get_task_node_for_run(run_id)
        if node:
            self.repo.update_generic("task_nodes", node["id"], {"run_id": retry.id, "status": "pending", "updated_at": now_iso()})
        self.events.append(
            retry.id,
            retry.session_id,
            "run.retry.created",
            "operator",
            "operator",
            "pending",
            {"retry_of": run_id, "attempt": self._retry_attempt(source)},
        )
        if execute_now:
            return {"retry_run_id": retry.id, **self.execute(retry.id)}
        return {"status": "pending", "retry_run_id": retry.id, "retry_of": run_id}

    def _retry_attempt(self, source: dict) -> int:
        metadata = source.get("metadata") or {}
        try:
            return int(metadata.get("attempt", 0)) + 1
        except (TypeError, ValueError):
            return 1

    def create_checkpoint(self, session_id: str, label: str = "自动检查点", reason: str = "") -> dict:
        session = self.repo.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        runs = self.repo.list_runs_for_session(session_id)
        nodes = self.repo.list_task_nodes_for_session(session_id)
        artifacts = self.repo.list_artifacts_for_session(session_id)
        checkpoint_id = self.repo.insert_generic(
            "session_checkpoints",
            {
                "session_id": session_id,
                "run_id": next((run["id"] for run in reversed(runs) if run["status"] == "completed"), None),
                "label": label,
                "reason": reason,
                "snapshot": {
                    "session_status": session["status"],
                    "run_ids": [run["id"] for run in runs],
                    "node_ids": [node["id"] for node in nodes],
                    "artifact_ids": [artifact["id"] for artifact in artifacts],
                    "runs": {run["id"]: run["status"] for run in runs},
                    "nodes": {node["id"]: node["status"] for node in nodes},
                },
                "status": "active",
                "created_at": now_iso(),
            },
        )
        run_id = next((run["id"] for run in reversed(runs) if run["status"] == "completed"), None)
        if run_id:
            self.events.append(run_id, session_id, "checkpoint.created", "system", "run_service", "completed", {"checkpoint_id": checkpoint_id, "label": label})
        return self.repo.get_checkpoint(checkpoint_id) or {"id": checkpoint_id, "session_id": session_id, "label": label}

    def rollback_session(self, session_id: str, checkpoint_id: str, reason: str = "operator rollback", actor_id: str = "operator") -> dict:
        checkpoint = self.repo.get_checkpoint(checkpoint_id)
        if not checkpoint or checkpoint["session_id"] != session_id:
            raise KeyError(checkpoint_id)
        snapshot = checkpoint.get("snapshot") or {}
        kept_runs = set(snapshot.get("run_ids", []))
        kept_nodes = set(snapshot.get("node_ids", []))
        for run in self.repo.list_runs_for_session(session_id):
            if run["id"] not in kept_runs and run["status"] in {"pending", "queued", "running", "paused"}:
                self.repo.update_run_status(run["id"], "cancelled", error=f"rolled back to checkpoint {checkpoint_id}")
        for node in self.repo.list_task_nodes_for_session(session_id):
            if node["id"] not in kept_nodes and node["status"] not in {"completed", "cancelled"}:
                self.repo.update_generic("task_nodes", node["id"], {"status": "cancelled", "updated_at": now_iso()})
        rollback_id = self.repo.insert_generic(
            "rollback_events",
            {
                "session_id": session_id,
                "checkpoint_id": checkpoint_id,
                "actor_id": actor_id,
                "reason": reason,
                "created_at": now_iso(),
            },
        )
        self.repo.update_session_status(session_id, "paused", f"Rolled back to {checkpoint.get('label', checkpoint_id)}")
        event_run = checkpoint.get("run_id") or next((run["id"] for run in self.repo.list_runs_for_session(session_id)), None)
        if event_run:
            self.events.append(event_run, session_id, "session.rollback.applied", "operator", actor_id, "paused", {"checkpoint_id": checkpoint_id, "rollback_id": rollback_id, "reason": reason})
        return {"status": "paused", "session_id": session_id, "checkpoint": checkpoint, "rollback_id": rollback_id, "mode": "append_only_logical_restore"}

    def pause_session(self, session_id: str, reason: str = "operator requested pause") -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        changed = [self.pause_run(run["id"], reason) for run in runs if run["status"] not in {"completed", "failed", "rejected", "cancelled", "timeout", "paused"}]
        if self.queue:
            self.queue.cancel_session(session_id)
        self.repo.update_session_status(session_id, "paused", reason)
        return {"status": "paused", "session_id": session_id, "changed": changed}

    def cancel_session(self, session_id: str, reason: str = "operator cancelled session") -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        changed = [self.cancel_run(run["id"], reason) for run in runs if run["status"] not in {"completed", "failed", "rejected", "cancelled", "timeout"}]
        if self.queue:
            self.queue.cancel_session(session_id)
        self.repo.update_session_status(session_id, "cancelled", reason)
        return {"status": "cancelled", "session_id": session_id, "changed": changed}

    def resume_session(self, session_id: str, execute_now: bool = False) -> dict:
        runs = self.repo.list_runs_for_session(session_id)
        changed = [self.resume_run(run["id"], execute_now=False) for run in runs if run["status"] == "paused"]
        self.repo.update_session_status(session_id, "pending", "operator resumed session")
        result: dict[str, object] = {"status": "pending", "session_id": session_id, "changed": changed}
        if execute_now:
            result["execution"] = self.execute_session_pending(session_id)
        return result

    def execute_session_pending(self, session_id: str) -> dict:
        pending_plan = self.repo.get_plan_for_session(session_id)
        session = self.repo.get_session(session_id) or {}
        if session.get("status") in {"needs_replan", "replanning", "paused", "cancelled"}:
            return {"session_id": session_id, "executed": 0, "status": session["status"]}
        if self.leader_workflow and self.leader_workflow.is_managed(session_id):
            reason = self.leader_workflow.readiness(session_id)
            if reason:
                return {"session_id": session_id, "executed": 0, "status": "blocked", "reason": reason}
        if pending_plan and pending_plan.get("status") in {"awaiting_approval", "needs_replan", "rejected"}:
            self.repo.update_session_status(session_id, "awaiting_approval", "plan approval is required before execution")
            return {
                "session_id": session_id,
                "executed": 0,
                "status": "awaiting_approval",
                "pending_plan_approval": 1,
                "plan_id": pending_plan["id"],
            }
        pending_approvals = self.repo.query_all(
            "approvals",
            "WHERE status = 'pending' AND run_id IN (SELECT id FROM runs WHERE session_id = ?)",
            (session_id,),
        )
        pending_delegations = self.repo.query_all(
            "delegation_requests",
            "WHERE status = 'pending' AND session_id = ?",
            (session_id,),
        )
        if pending_approvals or pending_delegations:
            self.repo.update_session_status(session_id, "awaiting_approval", "human approval is required before execution")
            return {
                "session_id": session_id,
                "executed": 0,
                "status": "awaiting_approval",
                "pending_approvals": len(pending_approvals),
                "pending_delegations": len(pending_delegations),
            }
        results: dict[str, dict] = {}
        planned_nodes = self.repo.list_task_nodes_for_session(session_id)
        if planned_nodes:
            while True:
                ready_nodes = [
                    node
                    for node in self.repo.list_task_nodes_for_session(session_id)
                    if node["status"] in {"pending", "queued", "blocked"} and node.get("run_id") and self.planning.is_node_ready(node)
                ]
                ready_run_ids = [node["run_id"] for node in ready_nodes if node["run_id"] not in results and self.repo.get_run(node["run_id"]) and self.repo.get_run(node["run_id"])["status"] == "pending"]
                if not ready_run_ids:
                    break
                for run_id in ready_run_ids:
                    results[run_id] = self.execute(run_id)
            self._finalize_session_after_run(session_id)
            blocked = [result for result in results.values() if result.get("status") == "blocked"]
            return {"session_id": session_id, "executed": len(results) - len(blocked), "results": results,
                    "status": "blocked" if blocked else (self.repo.get_session(session_id) or {}).get("status"),
                    "reason": next((r.get("reason") or r.get("error") for r in blocked), None)}

        runs = self.repo.list_runs_for_session(session_id)
        for run in runs:
            if run["status"] == "pending":
                results[run["id"]] = self.execute(run["id"])
        if results:
            self._finalize_session_after_run(session_id)
        return {"session_id": session_id, "executed": len(results), "results": results,
                "status": (self.repo.get_session(session_id) or {}).get("status")}

    def create_story_session(self, owner_id: str = "operator", execute_now: bool = True) -> dict:
        session = self.create_session(
            title="双 Agent 写作与评价 Session",
            owner_id=owner_id,
            root_agent_id="story_writer",
            team_id="story_team",
            objective="写作并评审一个故事，保存故事和评审产物",
        )
        self.repo.update_session_status(session.id, "running", "story_writer writes a story, story_reviewer reviews it")

        writer = self.create_run(session.id, "story_writer", "写一个 300 字以内的小故事，并保存为 story.md")
        reviewer = self.create_run(
            session.id,
            "story_reviewer",
            "阅读 story.md，写一份结构化故事评价，并保存为 review.md",
            parent_run_id=writer.id,
        )
        if not execute_now:
            return {"session_id": session.id, "run_ids": [writer.id, reviewer.id], "executed": False}

        writer_result = self._execute_story_writer(writer.id)
        reviewer_result = self._execute_story_reviewer(reviewer.id)
        final_status = "completed" if writer_result["status"] == reviewer_result["status"] == "completed" else "failed"
        self.repo.update_session_status(
            session.id,
            final_status,
            "story.md and review.md created" if final_status == "completed" else "story demo failed; inspect run errors",
        )
        return {
            "session_id": session.id,
            "run_ids": [writer.id, reviewer.id],
            "executed": True,
            "status": final_status,
            "writer": writer_result,
            "reviewer": reviewer_result,
        }

    def create_team_task(
        self,
        *,
        title: str,
        owner_id: str,
        team_id: str,
        leader: str,
        members: list[str],
        input_summary: str,
        strategy: str,
        execute_now: bool = True,
        require_plan_approval: bool = False,
        knowledge_sources: list[dict] | None = None,
        knowledge_policy: dict | None = None,
    ) -> dict:
        execute_now = execute_now and not require_plan_approval
        session = self.create_session(
            title=title,
            owner_id=owner_id,
            root_agent_id=leader,
            team_id=team_id,
            knowledge_sources=knowledge_sources,
            knowledge_policy=knowledge_policy,
            objective=input_summary,
        )
        self.repo.update_session_status(session.id, "running" if execute_now else "pending", f"{strategy}: {input_summary}")
        self._ensure_session_agents(session.id, leader, members)
        plan_nodes = self.planner.plan(objective=input_summary, strategy=strategy, leader=leader, members=members)
        run_ids_by_node_key: dict[str, str] = {}
        run_ids: list[str] = []
        for node in plan_nodes:
            parent_run_id = None
            if node.depends_on:
                parent_run_id = run_ids_by_node_key.get(node.depends_on[0])
            run = self.create_run(session.id, node.assigned_agent_id, node.instruction, parent_run_id=parent_run_id)
            run_ids_by_node_key[node.node_key] = run.id
            run_ids.append(run.id)

        parent_run_id = run_ids[0] if run_ids else None
        for node in plan_nodes:
            run_id = run_ids_by_node_key[node.node_key]
            self.repo.insert_generic(
                "agent_messages",
                {
                    "trace_id": parent_run_id or run_id,
                    "session_id": session.id,
                    "parent_run_id": parent_run_id,
                    "source_agent_id": leader,
                    "target_agent_id": node.assigned_agent_id,
                    "message_type": "task.assigned",
                    "payload": {
                        "strategy": strategy,
                        "node_key": node.node_key,
                        "title": node.title,
                        "instruction": node.instruction,
                        "depends_on": node.depends_on,
                        "required_tools": node.required_tools,
                        "output_contract": node.output_contract,
                    },
                    "status": "sent",
                    "created_at": now_iso(),
                },
            )
            self.repo.insert_generic(
                "collaboration_tasks",
                {
                    "parent_run_id": parent_run_id or run_id,
                    "assigned_agent_id": node.assigned_agent_id,
                    "task_type": "planner_node" if node.assigned_agent_id == leader else "worker",
                    "instruction": node.instruction,
                    "status": "pending",
                    "result_summary": None,
                    "created_at": now_iso(),
                },
            )
        plan_bundle = self.planning.create_plan(
            session_id=session.id,
            objective=input_summary,
            strategy=strategy,
            planner_agent_id=leader,
            nodes=plan_nodes,
            run_ids_by_node_key=run_ids_by_node_key,
            requirement_id=(self.repo.get_current_requirement(session.id) or {}).get("id"),
            approval_status="approved" if execute_now else "pending",
        )
        if require_plan_approval:
            plan = self.repo.get_plan_for_session(session.id)
            self.repo.update_generic("session_plans", plan["id"], {
                "status": "awaiting_approval", "approval_status": "required", "updated_at": now_iso(),
            })
            self.repo.update_session_status(session.id, "awaiting_approval", "Leader initial plan is waiting for human approval")
            if parent_run_id:
                self.events.append(parent_run_id, session.id, "session.plan.awaiting_approval", "planner", leader,
                                   "awaiting_approval", {"plan_id": plan["id"], "requirement_id": plan.get("requirement_id")})
            plan_bundle = self.planning.get_plan_bundle(session.id)
        checkpoint = self.create_checkpoint(session.id, "初始计划检查点", "Leader 计划已生成，执行前保留可回滚基线")
        results: dict[str, dict] = {}
        if execute_now:
            execution = self.execute_session_pending(session.id)
            results = execution["results"]

        return {
            "session_id": session.id,
            "parent_run_id": parent_run_id,
            "child_run_ids": run_ids[1:],
            "run_ids": run_ids,
            "team_id": team_id,
            "strategy": strategy,
            "executed": execute_now,
            "status": self.repo.get_session(session.id)["status"],
            "results": results,
            **plan_bundle,
            "checkpoint": checkpoint,
        }

    def _record_child_result_message(self, run_id: str, result: dict) -> None:
        run = self.repo.get_run(run_id)
        if not run or not run.get("parent_run_id"):
            return
        parent = self.repo.get_run(run["parent_run_id"])
        if not parent:
            return
        self.repo.insert_generic(
            "agent_messages",
            {
                "trace_id": parent["id"],
                "session_id": run["session_id"],
                "parent_run_id": parent["id"],
                "source_agent_id": run["agent_id"],
                "target_agent_id": parent["agent_id"],
                "message_type": "task.result",
                "payload": {
                    "child_run_id": run_id,
                    "status": "completed",
                    "summary": result.get("response", "")[:500],
                    "tool_results": result.get("tool_results", []),
                },
                "status": "sent",
                "created_at": now_iso(),
            },
        )
        self.events.append(
            run_id,
            run["session_id"],
            "agent.message.sent",
            "agent",
            run["agent_id"],
            "completed",
            {"target_agent_id": parent["agent_id"], "message_type": "task.result"},
        )

    def _finalize_session_after_run(self, session_id: str) -> None:
        session = self.repo.get_session(session_id) or {}
        if session.get("status") in {"needs_replan", "awaiting_approval", "paused", "cancelled"}:
            return
        runs = self.repo.list_runs_for_session(session_id)
        nodes = self.repo.list_task_nodes_for_session(session_id)
        retired_run_ids = {node["run_id"] for node in nodes if node["status"] == "superseded"}
        retired_run_ids.update(run["metadata"]["retry_of"] for run in runs if run.get("metadata", {}).get("retry_of"))
        runs = [run for run in runs if run["id"] not in retired_run_ids and run.get("run_type") != "leader_planning"]
        if not runs:
            return
        statuses = {run["status"] for run in runs}
        terminal = {"completed", "failed", "rejected", "cancelled", "timeout"}
        if any(status in {"failed", "rejected", "timeout"} for status in statuses):
            self.repo.update_session_status(session_id, "failed", "one or more runs failed")
            return
        if all(status in terminal for status in statuses):
            if any(status == "cancelled" for status in statuses):
                self.repo.update_session_status(session_id, "cancelled", "one or more runs were cancelled")
            else:
                plan = self.repo.get_plan_for_session(session_id)
                if plan and plan["status"] == "active" and all(n["status"] == "completed" for n in nodes if n["status"] != "superseded"):
                    self.repo.update_generic("session_plans", plan["id"], {"status": "completed", "updated_at": now_iso()})
                self.repo.update_session_status(session_id, "completed", "执行完成，等待用户验收")
            return
        if any(status == "running" for status in statuses):
            self.repo.update_session_status(session_id, "running", "runs are still executing")
        else:
            self.repo.update_session_status(session_id, "pending", "waiting for remaining runs")

    def _member_instruction(self, strategy: str, input_summary: str, member: str) -> str:
        if strategy == "parallel_review":
            return f"从 {member} 的专业视角独立评审这个任务，输出风险、证据和建议：{input_summary}"
        if strategy == "planner_executor_reviewer":
            role_hint = {
                "evidence": "收集证据和上下文",
                "execution": "执行受限检查或验证",
                "policy_auditor": "审查权限、预算、HITL 和审计链",
                "reviewer": "评审最终结论是否有证据支撑",
            }.get(member, "完成分配给你的子任务")
            return f"{role_hint}。总任务：{input_summary}"
        return f"按 {strategy} 策略完成你的子任务。总任务：{input_summary}"

    def _execute_story_writer(self, run_id: str) -> dict:
        return self._execute_model_then_file(
            run_id,
            agent_id="story_writer",
            prompt=(
                "请写一个 300 字以内的小故事。要求：有标题、人物、冲突和结尾；"
                "直接输出故事正文，不要解释你将如何写。"
            ),
            output_path="story.md",
        )

    def _execute_story_reviewer(self, run_id: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        story = self.loop.tool_gateway.call(run_id, run["session_id"], "story_reviewer", "file_read", {"path": "story.md"})
        if story.get("status") != "completed":
            message = story.get("error") or "file_read failed for story.md"
            self.repo.update_run_status(run_id, "failed", error=message)
            self.events.append(run_id, run["session_id"], "run.failed", "system", "run_service", "failed", {"status": "failed", "error": message})
            return {"status": "failed", "response": "", "error": message}
        story_text = story.get("content", "")
        return self._execute_model_then_file(
            run_id,
            agent_id="story_reviewer",
            prompt=(
                "请评价下面这个小故事，输出：优点、问题、可修改建议、总体评分。\n\n"
                f"故事：\n{story_text}"
            ),
            output_path="review.md",
        )

    def _execute_model_then_file(self, run_id: str, agent_id: str, prompt: str, output_path: str) -> dict:
        run = self.repo.get_run(run_id)
        if not run:
            raise KeyError(run_id)
        if run["status"] in {"completed", "failed", "rejected", "cancelled", "timeout"}:
            return {"status": run["status"], "response": run.get("output_summary") or "", "error": run.get("error")}
        ensure_transition(run["status"], "running")
        self.repo.update_run_status(run_id, "running")
        self.events.append(run_id, run["session_id"], "run.status_changed", "system", "run_service", "completed", {"from": run["status"], "to": "running"})
        try:
            response = self.loop.model_gateway.complete(run_id, run["session_id"], agent_id, prompt)
            tool_result = self.loop.tool_gateway.call(
                run_id,
                run["session_id"],
                agent_id,
                "file_write",
                {"path": output_path, "content": response.content},
            )
            if tool_result.get("status") != "completed":
                raise RuntimeError(tool_result.get("error") or f"file_write failed for {output_path}")
        except Exception as exc:
            message = str(exc)
            self.repo.update_run_status(run_id, "failed", error=message)
            self.repo.update_session_status(run["session_id"], "failed", message)
            self.events.append(run_id, run["session_id"], "run.failed", "system", "run_service", "failed", {"status": "failed", "error": message})
            return {"status": "failed", "response": "", "error": message}
        self.repo.update_run_status(run_id, "completed", output_summary=response.content)
        result = {"response": response.content, "tool_result": tool_result}
        self.events.append(run_id, run["session_id"], "run.final", "system", "run_service", "completed", {"status": "completed", "result": result})
        return {"status": "completed", **result}

