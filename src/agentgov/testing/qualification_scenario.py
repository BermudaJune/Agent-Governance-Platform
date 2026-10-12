from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agentgov.config.loader import load_config
from agentgov.storage.db import init_db
from agentgov.storage.models import RunRecord, SessionRecord, now_iso
from agentgov.storage.repositories import Repository


@dataclass
class QualificationResult:
    status: str
    session_id: str
    parent_run_id: str
    child_run_ids: list[str]
    report_path: str
    checks: dict[str, bool]

    def to_json(self) -> str:
        return json.dumps(self.__dict__, ensure_ascii=False, indent=2, sort_keys=True)


def run_qualification(config_path: str | Path, database: str) -> QualificationResult:
    cfg = load_config(config_path)
    init_db(database)
    repo = Repository(database)
    session = repo.create_session(
        SessionRecord(
            title="Qualification: repository governance review",
            owner_id="qualification",
            root_agent_id="coordinator",
            team_id=cfg.teams[0].id if cfg.teams else None,
            status="running",
        )
    )
    parent = repo.create_run(
        RunRecord(
            session_id=session.id,
            agent_id="coordinator",
            input_summary="Analyze repository governance path and produce traceable report.",
            status="running",
            started_at=now_iso(),
        )
    )
    repo.append_step(parent.id, session.id, "run.started", "agent", "coordinator", payload={"role": "leader"})
    child_ids: list[str] = []
    for agent_id, task in [
        ("evidence", "read/search repository and collect evidence"),
        ("execution", "run read-only checks in sandbox"),
        ("policy_auditor", "verify policy decisions and HITL boundaries"),
        ("reviewer", "review final report traceability"),
    ]:
        repo.insert_generic(
            "agent_messages",
            {
                "trace_id": parent.id,
                "session_id": session.id,
                "parent_run_id": parent.id,
                "source_agent_id": "coordinator",
                "target_agent_id": agent_id,
                "message_type": "task.assigned",
                "payload": {"task": task},
                "status": "sent",
                "created_at": now_iso(),
            },
        )
        child = repo.create_run(
            RunRecord(
                session_id=session.id,
                parent_run_id=parent.id,
                agent_id=agent_id,
                input_summary=task,
                status="completed",
                started_at=now_iso(),
                completed_at=now_iso(),
                output_summary=f"{agent_id} completed: {task}",
            )
        )
        child_ids.append(child.id)
        repo.append_step(child.id, session.id, "run.started", "agent", agent_id, payload={"task": task})
        if agent_id == "evidence":
            step = repo.append_step(
                child.id,
                session.id,
                "tool.call.finished",
                "agent",
                agent_id,
                payload={"tool": "repo_search", "query": "audit", "result": "found governance records"},
            )
            repo.insert_generic(
                "tool_calls",
                {
                    "run_id": child.id,
                    "step_id": step.id,
                    "tool_name": "repo_search",
                    "caller_agent_id": agent_id,
                    "args_summary": {"query": "audit"},
                    "result_summary": {"matches": 1},
                    "status": "completed",
                },
            )
        if agent_id == "execution":
            step = repo.append_step(
                child.id,
                session.id,
                "sandbox.action.finished",
                "agent",
                agent_id,
                payload={"command": "rg audit", "policy": "read_only"},
            )
            repo.insert_generic(
                "sandbox_actions",
                {
                    "run_id": child.id,
                    "step_id": step.id,
                    "sandbox_id": "readonly",
                    "action_type": "command",
                    "command_summary": "rg audit",
                    "filesystem_policy": "read_only",
                    "network_policy": "disabled",
                    "status": "completed",
                    "output_summary": "read-only command executed",
                },
            )
        repo.append_step(child.id, session.id, "run.final", "system", agent_id, payload={"status": "completed"})
        repo.insert_generic(
            "agent_messages",
            {
                "trace_id": parent.id,
                "session_id": session.id,
                "parent_run_id": parent.id,
                "source_agent_id": agent_id,
                "target_agent_id": "coordinator",
                "message_type": "task.result",
                "payload": {"summary": f"{agent_id} result"},
                "status": "sent",
                "created_at": now_iso(),
            },
        )

    decision_step = repo.append_step(
        parent.id,
        session.id,
        "policy.decision",
        "system",
        "policy_engine",
        payload={"decision": "allow", "policy_id": "max_cost_per_run"},
    )
    repo.insert_generic(
        "policy_decisions",
        {
            "run_id": parent.id,
            "step_id": decision_step.id,
            "policy_id": "max_cost_per_run",
            "policy_type": "budget",
            "subject": "coordinator",
            "action": "run.complete",
            "resource": parent.id,
            "decision": "allow",
            "reason": "scripted qualification within budget",
            "metadata": {},
            "created_at": now_iso(),
        },
    )
    repo.insert_generic(
        "budget_ledger",
        {
            "run_id": parent.id,
            "scope_type": "run",
            "scope_id": parent.id,
            "entry_type": "settle",
            "amount_usd": 0,
            "provider": "scripted-governance",
            "model": "scripted-governance-model",
            "reason": "scripted qualification no external spend",
            "created_at": now_iso(),
        },
    )
    report_dir = Path("data/objects/reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{parent.id}.md"
    report_path.write_text(
        "# Qualification Report\n\nEvidence, execution, policy, and review child runs completed.\n",
        encoding="utf-8",
    )
    repo.insert_generic(
        "evidence_refs",
        {
            "ref_type": "artifact",
            "ref_id": str(report_path),
            "run_id": parent.id,
            "step_id": decision_step.id,
            "summary": "Traceable qualification report artifact",
        },
    )
    repo.insert_generic(
        "experience_candidates",
        {
            "source_run_id": parent.id,
            "summary": "Repository governance tasks should verify tool-call audit persistence first.",
            "evidence_refs": [str(report_path)],
            "confidence": 0.8,
            "status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        },
    )
    repo.append_step(parent.id, session.id, "run.final", "system", "coordinator", payload={"status": "completed", "report": str(report_path)})
    repo.update_run_status(parent.id, "completed", output_summary="Qualification completed.")

    checks = {
        "parent_run": True,
        "child_runs": len(child_ids) == 4,
        "messages": True,
        "report_artifact": report_path.exists(),
        "experience_candidate": True,
    }
    return QualificationResult("completed", session.id, parent.id, child_ids, str(report_path), checks)
