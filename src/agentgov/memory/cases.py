from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from agentgov.storage.db import connect
from agentgov.storage.models import new_id, now_iso
from agentgov.storage.repositories import Repository, _row_to_dict


class CaseConflict(ValueError):
    pass


def _tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9_]{2,}", text.lower()))
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        words.update(segment[i:i + 2] for i in range(len(segment) - 1))
    return words


class SessionCaseService:
    """Archive explicit reviews; recall only the method text an operator shared."""

    def __init__(self, repo: Repository):
        self.repo = repo

    def _snapshot(self, conn, session_id: str) -> dict:
        def rows(sql: str) -> list[dict]:
            return [_row_to_dict(row) for row in conn.execute(sql, (session_id,)).fetchall()]

        sessions = rows("SELECT * FROM sessions WHERE id = ?")
        if not sessions:
            raise KeyError(session_id)
        session = sessions[0]
        runs = rows("SELECT * FROM runs WHERE session_id = ? ORDER BY created_at, id")
        nodes = rows("SELECT * FROM task_nodes WHERE session_id = ? ORDER BY created_at, id")
        retired = {node["run_id"] for node in nodes if node["status"] == "superseded"}
        retired.update(run["metadata"]["retry_of"] for run in runs if run.get("metadata", {}).get("retry_of"))
        live_runs = [run for run in runs if run["id"] not in retired]
        requirements = rows("SELECT * FROM session_requirements WHERE session_id = ? ORDER BY version, id")
        plans = rows("SELECT * FROM session_plans WHERE session_id = ? ORDER BY version, created_at, id")
        artifacts = rows("SELECT * FROM artifacts WHERE session_id = ? ORDER BY created_at, id")
        versions = rows("SELECT * FROM artifact_versions WHERE session_id = ? ORDER BY created_at, id")
        approvals = rows("SELECT * FROM approvals WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?) ORDER BY id")
        feedback = rows("SELECT * FROM session_feedback WHERE session_id = ? ORDER BY created_at, id")
        delegations = rows("SELECT * FROM delegation_requests WHERE session_id = ? ORDER BY id")
        rollbacks = rows("SELECT * FROM rollback_events WHERE session_id = ? ORDER BY created_at, id")
        # Audit events added by a review must not invalidate the execution being reviewed.
        fingerprint = {
            "status": session["status"], "requirements": requirements, "plans": plans,
            "runs": runs, "nodes": nodes, "artifacts": artifacts, "versions": versions,
            "approvals": approvals, "feedback": feedback, "delegations": delegations, "rollbacks": rollbacks,
        }
        snapshot_key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        terminal = {"completed", "failed", "rejected", "cancelled", "timeout"}
        settled = bool(live_runs) and all(run["status"] in terminal for run in live_runs)
        pending = any(item["status"] == "pending" for item in approvals) or any(
            item["status"] in {"pending", "awaiting_approval"} for item in delegations
        )
        plan = plans[-1] if plans else None
        clean_plan = not plan or (plan["status"] == "completed" and plan.get("approval_status") == "approved")
        ready = (
            session["status"] == "completed" and settled and not pending and clean_plan
            and all(run["status"] == "completed" for run in live_runs)
            and all(node["status"] == "completed" for node in nodes if node["status"] != "superseded")
            and not any(item.get("metadata", {}).get("stale") for item in artifacts if item["run_id"] not in retired)
        )
        return {
            "session": session, "snapshot_key": snapshot_key, "can_accept": ready,
            "can_close": settled and session["status"] in {"failed", "cancelled"},
            "runs": runs, "nodes": nodes, "requirements": requirements, "plans": plans,
            "artifacts": artifacts, "artifact_versions": versions, "feedback": feedback,
            "approvals": approvals, "rollbacks": rollbacks,
        }

    def review_state(self, session_id: str) -> dict:
        with connect(self.repo.database) as conn:
            conn.execute("BEGIN")
            snapshot = self._snapshot(conn, session_id)
            cases = [_row_to_dict(row) for row in conn.execute(
                "SELECT * FROM session_cases WHERE session_id = ? ORDER BY created_at DESC", (session_id,),
            )]
        current = next((case for case in cases if case["snapshot_key"] == snapshot["snapshot_key"]), None)
        return {
            "snapshot_key": snapshot["snapshot_key"], "current_case": current, "cases": cases,
            "can_accept": snapshot["can_accept"] and current is None,
            "can_close": snapshot["can_close"] and current is None,
            "execution_status": snapshot["session"]["status"],
            "recalled_cases": snapshot["session"]["metadata"].get("case_recall", []),
        }

    def archive(self, session_id: str, *, snapshot_key: str, outcome: str, reviewer_id: str,
                notes: str = "", satisfaction: int | None = None, reusable_guidance: str = "",
                share_scope: str = "private", tags: list[str] | None = None,
                proposal_target: str | None = None) -> dict:
        guidance = reusable_guidance.strip()
        if len(guidance) > 1500 or len(tags or []) > 12 or any(len(tag) > 48 for tag in tags or []):
            raise ValueError("方法最多 1500 字，最多 12 个标签，每个标签最多 48 字")
        if share_scope == "shared_methods" and not guidance:
            raise ValueError("共享前请填写可复用方法；原始资料和产物不会自动共享")
        with connect(self.repo.database) as conn:
            # One transaction covers validation, the immutable case, proposal and audit.
            conn.execute("BEGIN IMMEDIATE")
            snapshot = self._snapshot(conn, session_id)
            if snapshot_key != snapshot["snapshot_key"]:
                raise CaseConflict("Session 已发生变化，请刷新后验收当前版本")
            existing = conn.execute(
                "SELECT * FROM session_cases WHERE session_id = ? AND snapshot_key = ?", (session_id, snapshot_key),
            ).fetchone()
            if existing:
                return {"case": _row_to_dict(existing), "already_archived": True}
            if outcome == "accepted":
                if not snapshot["can_accept"]:
                    raise CaseConflict("执行、审批和当前计划尚未全部完成，暂不能验收")
            elif not snapshot["can_close"] or outcome != snapshot["session"]["status"]:
                raise CaseConflict("只能将已结束的失败或取消任务按其实际结果归档")
            if proposal_target and not guidance:
                raise ValueError("提出进化候选前请填写方法建议")
            data = self._case_data(conn, session_id, snapshot)
            case = {
                "id": new_id(), "session_id": session_id, "owner_id": snapshot["session"]["owner_id"],
                "snapshot_key": snapshot_key, "outcome": outcome, "reviewer_id": reviewer_id,
                "notes": notes.strip(), "satisfaction": satisfaction, "reusable_guidance": guidance,
                "share_scope": share_scope, "tags": list(dict.fromkeys(tag.strip() for tag in tags or [] if tag.strip())),
                "case_data": data, "created_at": now_iso(),
            }
            self._insert(conn, "session_cases", case)
            if proposal_target:
                self._insert(conn, "experience_candidates", {
                    "id": new_id(), "source_run_id": snapshot["runs"][0]["id"], "source_case_id": case["id"],
                    "summary": guidance, "evidence_refs": [case["id"], *data["audit_step_ids"]],
                    "target_type": proposal_target, "operation": "add", "confidence": 0,
                    "status": "pending", "created_at": case["created_at"], "updated_at": case["created_at"],
                })
            self._audit(conn, snapshot, "session.review.archived", reviewer_id, {
                "case_id": case["id"], "snapshot_key": snapshot_key, "outcome": outcome,
                "share_scope": share_scope, "proposal_target": proposal_target,
            })
            conn.commit()
        return {"case": case, "already_archived": False}

    def _case_data(self, conn, session_id: str, snapshot: dict) -> dict:
        def rows(sql: str) -> list[dict]:
            return [_row_to_dict(row) for row in conn.execute(sql, (session_id,))]

        calls = rows("SELECT * FROM model_calls WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)")
        messages = rows("SELECT * FROM agent_messages WHERE session_id = ?")
        events = rows("SELECT id, event_type, actor_id, status FROM run_steps WHERE session_id = ? ORDER BY created_at, id")
        edges = rows("SELECT * FROM task_edges WHERE plan_id IN (SELECT id FROM session_plans WHERE session_id = ?)")
        agents = rows("SELECT id, agent_id, origin, role FROM session_agents WHERE session_id = ?")
        evidence = rows("SELECT id, ref_type, ref_id, run_id FROM evidence_refs WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)")
        return {
            "schema_version": 1, "title": snapshot["session"]["title"],
            "objective": (snapshot["requirements"][0] if snapshot["requirements"] else {}).get("objective", ""),
            "requirements": [{key: item.get(key) for key in ("id", "version", "source", "parent_id", "change_reason")} for item in snapshot["requirements"]],
            "plans": [{key: plan.get(key) for key in ("id", "version", "requirement_id", "strategy", "status", "change_reason", "approval_status")} for plan in snapshot["plans"]],
            "dag": {"nodes": [{key: node.get(key) for key in ("id", "plan_id", "node_key", "title", "assigned_agent_id", "run_id", "status", "required_tools")} for node in snapshot["nodes"]], "edges": edges},
            "agents": agents, "corrections": snapshot["feedback"],
            "runs": [{key: run.get(key) for key in ("id", "agent_id", "agent_version_id", "status", "error", "input_tokens", "output_tokens", "actual_cost_usd")} for run in snapshot["runs"]],
            "artifact_refs": snapshot["artifacts"], "artifact_version_refs": snapshot["artifact_versions"],
            "evidence_refs": evidence, "rollback_refs": snapshot["rollbacks"],
            "audit_step_ids": [event["id"] for event in events],
            "decision_refs": [event for event in events if any(token in event["event_type"] for token in ("decided", "approval", "policy", "replan"))],
            "metrics": {
                "model_calls": len(calls), "failed_model_calls": sum(call["status"] == "failed" for call in calls),
                "input_tokens": sum(call["input_tokens"] for call in calls), "output_tokens": sum(call["output_tokens"] for call in calls),
                "cost_usd": sum(call["actual_cost_usd"] for call in calls), "agent_messages": len(messages),
                "run_outcomes": dict(Counter(run["status"] for run in snapshot["runs"])),
                "cost_basis": "recorded_model_calls", "quality_basis": "operator_review",
            },
            "root_cause_status": "unconfirmed", "analysis_basis": "recorded_facts_only",
        }

    def recall(self, owner_id: str, query: str) -> list[dict]:
        tokens = _tokens(query)
        if not tokens:
            return []
        candidates = self.repo.query_all(
            "session_cases", "WHERE owner_id = ? AND share_scope = 'shared_methods' ORDER BY created_at DESC LIMIT 500", (owner_id,),
        )
        scored = []
        for case in candidates:
            # Do not rank or expose other Sessions' private facts, objectives or artifact text.
            words = _tokens(case["reusable_guidance"] + " " + " ".join(case["tags"]))
            overlap = len(tokens & words)
            if overlap:
                scored.append((overlap / max(1, len(tokens | words)) ** 0.5, case))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [{
            "case_id": case["id"], "source_session_id": case["session_id"], "snapshot_key": case["snapshot_key"],
            "guidance": case["reusable_guidance"], "tags": case["tags"], "outcome": case["outcome"],
            "reviewed_at": case["created_at"], "reference_type": "historical_method",
        } for _, case in scored[:3]]

    def set_sharing(self, case_id: str, share_scope: str, actor_id: str) -> dict:
        with connect(self.repo.database) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM session_cases WHERE id = ?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            case = _row_to_dict(row)
            if share_scope == "shared_methods" and not case["reusable_guidance"]:
                raise ValueError("此案例未填写可共享方法")
            conn.execute("UPDATE session_cases SET share_scope = ? WHERE id = ?", (share_scope, case_id))
            self._audit(conn, self._snapshot(conn, case["session_id"]), "session.case.sharing_changed", actor_id, {
                "case_id": case_id, "previous_scope": case["share_scope"], "share_scope": share_scope,
                "effective_for": "new_sessions", "active_session_references": "pinned",
            })
            conn.commit()
        return {**case, "share_scope": share_scope}

    @staticmethod
    def _insert(conn, table: str, record: dict) -> None:
        values = [json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value for value in record.values()]
        conn.execute(f"INSERT INTO {table} ({', '.join(record)}) VALUES ({', '.join('?' for _ in record)})", values)

    def _audit(self, conn, snapshot: dict, event_type: str, actor_id: str, payload: dict) -> None:
        run_id = snapshot["runs"][0]["id"]
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM run_steps WHERE run_id = ?", (run_id,)).fetchone()[0]
        self._insert(conn, "run_steps", {
            "id": new_id(), "run_id": run_id, "session_id": snapshot["session"]["id"], "seq": seq,
            "event_type": event_type, "actor_type": "operator", "actor_id": actor_id,
            "status": "completed", "payload": payload, "created_at": now_iso(),
        })
