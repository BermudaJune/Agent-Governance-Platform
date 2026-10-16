from __future__ import annotations

import json
import sqlite3
from typing import Any

from agentgov.storage.db import connect
from agentgov.storage.models import RunRecord, RunStep, SessionRecord, now_iso, new_id


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for key in (
        "metadata",
        "payload",
        "args_summary",
        "result_summary",
        "action_summary",
        "attributes",
        "covered_capabilities",
        "missing_capabilities",
        "redundant_agents",
        "suggested_agents",
        "risk_items",
        "token_waste_warnings",
        "member_agent_ids",
        "capability_ids",
        "agent_capabilities",
        "arguments",
        "data",
        "raw_plan",
        "contract",
        "impact",
        "required_capabilities",
        "required_tools",
        "input_refs",
        "output_contract",
        "source_ids",
        "result_refs",
        "spec_snapshot",
        "requested_skills",
        "requested_tools",
        "snapshot",
        "tags",
        "case_data",
        "evidence_refs",
    ):
        if key in out and isinstance(out[key], str):
            out[key] = json.loads(out[key] or "{}")
    return out


class Repository:
    def __init__(self, database: str):
        self.database = database

    def create_session(self, record: SessionRecord) -> SessionRecord:
        with connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO sessions (
                  id, title, owner_id, root_agent_id, team_id, status, context_summary,
                  metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.title,
                    record.owner_id,
                    record.root_agent_id,
                    record.team_id,
                    record.status,
                    record.context_summary,
                    _json(record.metadata),
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()
        return record

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with connect(self.database) as conn:
            return _row_to_dict(conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())

    def list_sessions(self) -> list[dict[str, Any]]:
        with connect(self.database) as conn:
            return [_row_to_dict(row) for row in conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()]

    def update_session_status(self, session_id: str, status: str, context_summary: str | None = None) -> None:
        with connect(self.database) as conn:
            conn.execute(
                """
                UPDATE sessions
                SET status = ?, context_summary = COALESCE(?, context_summary), updated_at = ?
                WHERE id = ?
                """,
                (status, context_summary, now_iso(), session_id),
            )
            conn.commit()

    def create_requirement_version(
        self,
        session_id: str,
        objective: str,
        contract: dict[str, Any] | None = None,
        *,
        source: str = "user",
        parent_id: str | None = None,
        change_reason: str = "",
        created_by: str = "operator",
    ) -> dict[str, Any]:
        with connect(self.database) as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM session_requirements WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            version = int(row["next_version"])
            conn.execute(
                "UPDATE session_requirements SET status = 'superseded' WHERE session_id = ? AND status = 'active'",
                (session_id,),
            )
            record = {
                "session_id": session_id,
                "version": version,
                "objective": objective,
                "contract": contract or {},
                "source": source,
                "parent_id": parent_id,
                "change_reason": change_reason,
                "status": "active",
                "created_by": created_by,
                "created_at": now_iso(),
            }
            row_id = new_id()
            keys = ["id", *record.keys()]
            values = [row_id, *[_json(value) if isinstance(value, (dict, list)) else value for value in record.values()]]
            conn.execute(
                f"INSERT INTO session_requirements ({', '.join(keys)}) VALUES ({', '.join(['?'] * len(keys))})",
                values,
            )
            conn.commit()
        return self.get_requirement(row_id) or {"id": row_id, **record}

    def get_requirement(self, requirement_id: str) -> dict[str, Any] | None:
        rows = self.query_all("session_requirements", "WHERE id = ? LIMIT 1", (requirement_id,))
        return rows[0] if rows else None

    def get_current_requirement(self, session_id: str) -> dict[str, Any] | None:
        rows = self.query_all(
            "session_requirements",
            "WHERE session_id = ? AND status = 'active' ORDER BY version DESC LIMIT 1",
            (session_id,),
        )
        return rows[0] if rows else None

    def list_requirements_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_requirements", "WHERE session_id = ? ORDER BY version", (session_id,))

    def create_session_feedback(self, feedback: dict[str, Any]) -> dict[str, Any]:
        row_id = self.insert_generic(
            "session_feedback",
            {
                **feedback,
                "status": feedback.get("status", "submitted"),
                "created_by": feedback.get("created_by", "operator"),
                "created_at": feedback.get("created_at", now_iso()),
            },
        )
        return self.get_session_feedback(row_id) or {"id": row_id, **feedback}

    def get_session_feedback(self, feedback_id: str) -> dict[str, Any] | None:
        rows = self.query_all("session_feedback", "WHERE id = ? LIMIT 1", (feedback_id,))
        return rows[0] if rows else None

    def list_session_feedback(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_feedback", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_session_knowledge(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_knowledge_sources", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def add_session_knowledge(self, session_id: str, source: dict[str, Any]) -> str:
        return self.insert_generic(
            "session_knowledge_sources",
            {
                "session_id": session_id,
                "source_type": source.get("source_type", "session_note"),
                "name": source.get("name", "Session 知识"),
                "locator": source.get("locator"),
                "content": source.get("content", ""),
                "trust_level": source.get("trust_level", "session_input"),
                "required_citation": 1 if source.get("required_citation", True) else 0,
                "status": "active",
                "metadata": source.get("metadata", {}),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )

    def list_knowledge_grants(self, session_id: str, run_id: str | None = None) -> list[dict[str, Any]]:
        if run_id:
            return self.query_all("knowledge_access_grants", "WHERE session_id = ? AND run_id = ? ORDER BY created_at", (session_id, run_id))
        return self.query_all("knowledge_access_grants", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_knowledge_grants_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return self.query_all("knowledge_access_grants", "WHERE run_id = ? ORDER BY created_at", (run_id,))

    def create_run(self, record: RunRecord) -> RunRecord:
        with connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO runs (
                  id, session_id, parent_run_id, agent_id, agent_version_id, run_type,
                  status, input_summary, output_summary, error, estimated_cost_usd,
                  actual_cost_usd, input_tokens, output_tokens, started_at, completed_at,
                  metadata, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.session_id,
                    record.parent_run_id,
                    record.agent_id,
                    record.agent_version_id,
                    record.run_type,
                    record.status,
                    record.input_summary,
                    record.output_summary,
                    record.error,
                    record.estimated_cost_usd,
                    record.actual_cost_usd,
                    record.input_tokens,
                    record.output_tokens,
                    record.started_at,
                    record.completed_at,
                    _json(record.metadata),
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()
        return record

    def update_run_status(
        self,
        run_id: str,
        status: str,
        *,
        output_summary: str | None = None,
        error: str | None = None,
    ) -> None:
        completed_at = now_iso() if status in {"completed", "failed", "rejected", "cancelled", "timeout"} else None
        started_at = now_iso() if status == "running" else None
        with connect(self.database) as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = ?, output_summary = COALESCE(?, output_summary),
                    error = COALESCE(?, error), completed_at = COALESCE(?, completed_at),
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?
                WHERE id = ?
                """,
                (status, output_summary, error, completed_at, started_at, now_iso(), run_id),
            )
            conn.commit()

    def add_run_usage(self, run_id: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
        with connect(self.database) as conn:
            conn.execute(
                """
                UPDATE runs
                SET input_tokens = input_tokens + ?, output_tokens = output_tokens + ?,
                    actual_cost_usd = actual_cost_usd + ?, updated_at = ?
                WHERE id = ?
                """,
                (input_tokens, output_tokens, cost_usd, now_iso(), run_id),
            )
            conn.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with connect(self.database) as conn:
            return _row_to_dict(conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone())

    def list_runs(self) -> list[dict[str, Any]]:
        with connect(self.database) as conn:
            return [_row_to_dict(row) for row in conn.execute("SELECT * FROM runs ORDER BY created_at DESC").fetchall()]

    def list_runs_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with connect(self.database) as conn:
            return [
                _row_to_dict(row)
                for row in conn.execute("SELECT * FROM runs WHERE session_id = ? ORDER BY created_at", (session_id,)).fetchall()
            ]

    def list_runs_for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        with connect(self.database) as conn:
            return [
                _row_to_dict(row)
                for row in conn.execute("SELECT * FROM runs WHERE agent_id = ? ORDER BY created_at DESC", (agent_id,)).fetchall()
            ]

    def next_step_seq(self, run_id: str) -> int:
        with connect(self.database) as conn:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 AS next_seq FROM run_steps WHERE run_id = ?", (run_id,)).fetchone()
            return int(row["next_seq"])

    def append_step(
        self,
        run_id: str,
        session_id: str,
        event_type: str,
        actor_type: str,
        actor_id: str,
        status: str = "completed",
        payload: dict[str, Any] | None = None,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
    ) -> RunStep:
        step = RunStep(
            run_id=run_id,
            session_id=session_id,
            seq=self.next_step_seq(run_id),
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            status=status,
            payload=payload or {},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
        )
        with connect(self.database) as conn:
            conn.execute(
                """
                INSERT INTO run_steps (
                  id, run_id, session_id, parent_step_id, seq, event_type, actor_type,
                  actor_id, status, payload, input_tokens, output_tokens, cost_usd, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step.id,
                    step.run_id,
                    step.session_id,
                    step.parent_step_id,
                    step.seq,
                    step.event_type,
                    step.actor_type,
                    step.actor_id,
                    step.status,
                    _json(step.payload),
                    step.input_tokens,
                    step.output_tokens,
                    step.cost_usd,
                    step.created_at,
                ),
            )
            conn.commit()
        return step

    def list_steps(self, run_id: str) -> list[dict[str, Any]]:
        with connect(self.database) as conn:
            return [
                _row_to_dict(row)
                for row in conn.execute("SELECT * FROM run_steps WHERE run_id = ? ORDER BY seq", (run_id,)).fetchall()
            ]

    def insert_generic(self, table: str, data: dict[str, Any]) -> str:
        row = {"id": new_id(), **data}
        keys = list(row.keys())
        vals = [_json(row[k]) if isinstance(row[k], (dict, list)) else row[k] for k in keys]
        with connect(self.database) as conn:
            conn.execute(
                f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join(['?'] * len(keys))})",
                vals,
            )
            conn.commit()
        return row["id"]

    def query_all(self, table: str, where: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {table} {where}"
        with connect(self.database) as conn:
            return [_row_to_dict(row) for row in conn.execute(sql, params).fetchall()]

    def update_generic(self, table: str, row_id: str, data: dict[str, Any]) -> None:
        if not data:
            return
        keys = list(data.keys())
        vals = [_json(data[k]) if isinstance(data[k], (dict, list)) else data[k] for k in keys]
        assignments = ", ".join(f"{key} = ?" for key in keys)
        with connect(self.database) as conn:
            conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*vals, row_id))
            conn.commit()

    def insert_matching_report(self, report: dict[str, Any]) -> str:
        return self.insert_generic("team_matching_reports", report)

    def list_matching_reports_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("team_matching_reports", "WHERE session_id = ? ORDER BY created_at DESC", (session_id,))

    def insert_team_snapshot(self, snapshot: dict[str, Any]) -> str:
        return self.insert_generic("session_team_snapshots", snapshot)

    def get_team_snapshot_for_session(self, session_id: str) -> dict[str, Any] | None:
        rows = self.query_all("session_team_snapshots", "WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (session_id,))
        return rows[0] if rows else None

    def insert_team_template(self, template: dict[str, Any]) -> str:
        return self.insert_generic("team_templates", template)

    def list_team_templates(self) -> list[dict[str, Any]]:
        return self.query_all("team_templates", "ORDER BY updated_at DESC")

    def insert_artifact(self, artifact: dict[str, Any]) -> str:
        return self.insert_generic("artifacts", artifact)

    def list_artifacts_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("artifacts", "WHERE session_id = ? ORDER BY created_at DESC", (session_id,))

    def list_artifact_versions(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("artifact_versions", "WHERE session_id = ? ORDER BY created_at DESC", (session_id,))

    def list_session_agents(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_agents", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_delegation_requests(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("delegation_requests", "WHERE session_id = ? ORDER BY created_at DESC", (session_id,))

    def list_session_skill_grants(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_skill_grants", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_session_tool_grants(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_tool_grants", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_agent_lifecycle_events(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("agent_lifecycle_events", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_checkpoints", "WHERE session_id = ? ORDER BY created_at DESC", (session_id,))

    def get_checkpoint(self, checkpoint_id: str) -> dict[str, Any] | None:
        rows = self.query_all("session_checkpoints", "WHERE id = ? LIMIT 1", (checkpoint_id,))
        return rows[0] if rows else None

    def list_rollback_events(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("rollback_events", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def get_plan_for_session(self, session_id: str) -> dict[str, Any] | None:
        rows = self.query_all("session_plans", "WHERE session_id = ? ORDER BY created_at DESC LIMIT 1", (session_id,))
        return rows[0] if rows else None

    def list_plans_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("session_plans", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def list_task_nodes_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        return self.query_all("task_nodes", "WHERE plan_id = ? ORDER BY created_at", (plan_id,))

    def list_task_nodes_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all("task_nodes", "WHERE session_id = ? ORDER BY created_at", (session_id,))

    def get_task_node_for_run(self, run_id: str) -> dict[str, Any] | None:
        rows = self.query_all("task_nodes", "WHERE run_id = ? LIMIT 1", (run_id,))
        return rows[0] if rows else None

    def list_task_edges_for_plan(self, plan_id: str) -> list[dict[str, Any]]:
        return self.query_all("task_edges", "WHERE plan_id = ? ORDER BY created_at", (plan_id,))

    def list_task_edges_for_session(self, session_id: str) -> list[dict[str, Any]]:
        return self.query_all(
            "task_edges",
            "WHERE plan_id IN (SELECT id FROM session_plans WHERE session_id = ?) ORDER BY created_at",
            (session_id,),
        )
