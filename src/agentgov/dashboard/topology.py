from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from agentgov.config.loader import load_config
from agentgov.storage.repositories import Repository


def _node(node_id: str, node_type: str, label: str | None = None, status: str | None = None, **metadata: Any) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": label or node_id,
        "status": status,
        "metadata": metadata,
    }


def _edge(source: str, target: str, edge_type: str, **metadata: Any) -> dict:
    return {"source": source, "target": target, "type": edge_type, "metadata": metadata}


def _dedupe(nodes: list[dict], edges: list[dict]) -> dict:
    unique_nodes = {node["id"]: node for node in nodes}
    unique_edges = {}
    for index, edge in enumerate(edges):
        key = (edge["source"], edge["target"], edge["type"], str(edge.get("metadata", {})))
        unique_edges[key] = {"id": f"edge:{index}", **edge}
    return {"nodes": list(unique_nodes.values()), "edges": list(unique_edges.values())}


def topology(repo: Repository) -> dict:
    return agent_graph(repo)


def agent_graph(repo: Repository) -> dict:
    runs = repo.query_all("runs")
    messages = repo.query_all("agent_messages")
    tool_calls = repo.query_all("tool_calls")
    model_calls = repo.query_all("model_calls")
    budget = repo.query_all("budget_ledger")
    session_agents = repo.query_all("session_agents")

    nodes: list[dict] = []
    edges: list[dict] = []
    run_count = Counter(run["agent_id"] for run in runs)
    fail_count = Counter(run["agent_id"] for run in runs if run["status"] == "failed")
    spend_by_agent: Counter[str] = Counter()
    for entry in budget:
        if entry.get("entry_type") != "settle":
            continue
        run = next((item for item in runs if item["id"] == entry["run_id"]), None)
        if run:
            spend_by_agent[run["agent_id"]] += float(entry.get("amount_usd") or 0)

    for agent_id in sorted(run_count):
        nodes.append(
            _node(
                f"agent:{agent_id}",
                "agent",
                agent_id,
                "failed" if fail_count[agent_id] else "active",
                runs=run_count[agent_id],
                failures=fail_count[agent_id],
                spend_usd=round(spend_by_agent[agent_id], 6),
            )
        )

    for member in session_agents:
        node_id = f"session_agent:{member['id']}"
        nodes.append(_node(node_id, "session_agent", member["agent_id"], member["status"], session_id=member["session_id"], role=member["role"], origin=member["origin"], depth=member["depth"]))
        if member.get("parent_agent_id"):
            edges.append(_edge(f"agent:{member['parent_agent_id']}", node_id, "leader_creates_agent", session_id=member["session_id"]))

    for child in runs:
        if not child.get("parent_run_id"):
            continue
        parent = next((item for item in runs if item["id"] == child["parent_run_id"]), None)
        if parent:
            edges.append(_edge(f"agent:{parent['agent_id']}", f"agent:{child['agent_id']}", "parent_child", child_run_id=child["id"]))

    for message in messages:
        nodes.append(_node(f"agent:{message['source_agent_id']}", "agent", message["source_agent_id"]))
        nodes.append(_node(f"agent:{message['target_agent_id']}", "agent", message["target_agent_id"]))
        edges.append(
            _edge(
                f"agent:{message['source_agent_id']}",
                f"agent:{message['target_agent_id']}",
                message["message_type"],
                session_id=message["session_id"],
            )
        )

    for call in tool_calls:
        tool_id = f"tool:{call['tool_name']}"
        nodes.append(_node(tool_id, "tool", call["tool_name"], call["status"]))
        edges.append(_edge(f"agent:{call['caller_agent_id']}", tool_id, "calls_tool", status=call["status"]))

    for call in model_calls:
        model_id = f"model:{call['provider']}:{call['model']}"
        run = next((item for item in runs if item["id"] == call["run_id"]), None)
        nodes.append(_node(model_id, "model", f"{call['provider']} / {call['model']}", call["status"]))
        if run:
            edges.append(_edge(f"agent:{run['agent_id']}", model_id, "calls_model", status=call["status"]))

    return _dedupe(nodes, edges)


def session_graph(repo: Repository, session_id: str, current_only: bool = False) -> dict:
    session = repo.get_session(session_id)
    runs = repo.list_runs_for_session(session_id)
    task_nodes = repo.list_task_nodes_for_session(session_id)
    current_plan = repo.get_plan_for_session(session_id) if current_only else None
    if current_only:
        current_nodes = [node for node in task_nodes if node.get("status") != "superseded"]
        current_run_ids = {node["run_id"] for node in current_nodes}
        planning_run_id = ((session or {}).get("metadata", {}).get("leader") or {}).get("planning_run_id")
        if planning_run_id:
            current_run_ids.add(planning_run_id)
        runs = [run for run in runs if run["id"] in current_run_ids]
    run_ids = {run["id"] for run in runs}
    steps = repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,))
    messages = repo.query_all("agent_messages", "WHERE session_id = ? ORDER BY created_at", (session_id,))
    if current_only:
        current_plan_id = (current_plan or {}).get("id")
        messages = [message for message in messages if _message_belongs_to_current(message, run_ids, current_plan_id)]
    model_calls = [row for row in repo.query_all("model_calls", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,)) if row["run_id"] in run_ids]
    tool_calls = [row for row in repo.query_all("tool_calls", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,)) if row["run_id"] in run_ids]
    evidence_refs = [row for row in repo.query_all("evidence_refs", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,)) if row["run_id"] in run_ids]
    approvals = [row for row in repo.query_all("approvals", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,)) if row["run_id"] in run_ids]
    policies = [row for row in repo.query_all("policy_decisions", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,)) if row["run_id"] in run_ids]
    session_agents = repo.list_session_agents(session_id)
    delegation_requests = repo.list_delegation_requests(session_id)
    skill_grants = repo.list_session_skill_grants(session_id)
    tool_grants = repo.list_session_tool_grants(session_id)
    lifecycle_events = repo.list_agent_lifecycle_events(session_id)
    if current_only:
        session_agents = [row for row in session_agents if row["status"] == "active"]
        delegation_requests = [row for row in delegation_requests if row["status"] in {"pending", "approved"}]
        skill_grants = [row for row in skill_grants if row["status"] == "active"]
        tool_grants = [row for row in tool_grants if row["status"] == "active"]
        lifecycle_events = []

    nodes: list[dict] = []
    edges: list[dict] = []
    task_id = f"session:{session_id}"
    nodes.append(_node(task_id, "session", session["title"] if session else session_id, session["status"] if session else None))

    for member in session_agents:
        agent_node = f"session_agent:{member['id']}"
        nodes.append(_node(agent_node, "session_agent", member["agent_id"], member["status"], role=member["role"], origin=member["origin"], depth=member["depth"], spec_snapshot=member.get("spec_snapshot", {})))
        if member.get("parent_agent_id"):
            parent = next((item for item in session_agents if item["agent_id"] == member["parent_agent_id"]), None)
            edges.append(_edge(f"session_agent:{parent['id']}" if parent else task_id, agent_node, "leader_creates_agent", origin=member["origin"]))
        else:
            edges.append(_edge(task_id, agent_node, "has_leader"))

    for run in runs:
        run_id = f"run:{run['id']}"
        nodes.append(_node(run_id, "run", run["agent_id"], run["status"], input=run["input_summary"], error=run.get("error")))
        if run.get("parent_run_id"):
            source = f"run:{run['parent_run_id']}" if run["parent_run_id"] in run_ids else task_id
            edges.append(_edge(source, run_id, "delegates_to", agent_id=run["agent_id"]))
        else:
            edges.append(_edge(task_id, run_id, "starts", agent_id=run["agent_id"]))

    for message in messages:
        source_run_id, target_run_id = _message_run_ids(message, runs, task_nodes)
        if source_run_id and target_run_id:
            edges.append(
                _edge(
                    f"run:{source_run_id}",
                    f"run:{target_run_id}",
                    message["message_type"],
                    payload=message.get("payload", {}),
                )
            )

    for index, call in enumerate(model_calls, 1):
        node_id = f"model_call:{call['id']}"
        nodes.append(
            _node(
                node_id,
                "model_call",
                f"{call['model']} #{index}",
                call["status"],
                input_tokens=call.get("input_tokens"),
                output_tokens=call.get("output_tokens"),
                cost_usd=call.get("actual_cost_usd"),
            )
        )
        edges.append(_edge(f"run:{call['run_id']}", node_id, "calls_model"))

    for call in tool_calls:
        node_id = f"tool_call:{call['id']}"
        nodes.append(_node(node_id, "tool_call", call["tool_name"], call["status"], args=call.get("args_summary"), result=call.get("result_summary")))
        edges.append(_edge(f"run:{call['run_id']}", node_id, "calls_tool", tool=call["tool_name"]))

    for ref in evidence_refs:
        artifact_id = f"artifact:{ref['id']}"
        label = Path(ref.get("path") or ref["ref_id"]).name
        nodes.append(_node(artifact_id, "artifact", label, "created", path=ref.get("path"), summary=ref.get("summary")))
        source = _tool_call_for_step(tool_calls, ref.get("step_id"))
        edges.append(_edge(f"tool_call:{source['id']}" if source else f"run:{ref['run_id']}", artifact_id, "writes_artifact" if ref["ref_type"] == "artifact" else "reads_artifact"))

    for approval in approvals:
        node_id = f"approval:{approval['id']}"
        nodes.append(_node(node_id, "approval", "人工审批", approval["status"], reason=approval.get("reason")))
        edges.append(_edge(f"run:{approval['run_id']}", node_id, "requires_approval"))

    for decision in policies:
        node_id = f"policy:{decision['id']}"
        nodes.append(_node(node_id, "policy", decision["policy_id"], decision["decision"], reason=decision.get("reason")))
        edges.append(_edge(f"run:{decision['run_id']}", node_id, "checked_by_policy"))

    for request in delegation_requests:
        request_node = f"delegation:{request['id']}"
        nodes.append(_node(request_node, "delegation_request", request.get("requested_role", "delegation"), request["status"], objective=request.get("objective"), risk_level=request.get("risk_level"), requested_skills=request.get("requested_skills", []), requested_tools=request.get("requested_tools", [])))
        parent = next((item for item in session_agents if item["agent_id"] == request["parent_agent_id"]), None)
        edges.append(_edge(f"session_agent:{parent['id']}" if parent else task_id, request_node, "requests_delegation"))
        if request.get("requested_agent_id"):
            target = next((item for item in session_agents if item["agent_id"] == request["requested_agent_id"]), None)
            if target:
                edges.append(_edge(request_node, f"session_agent:{target['id']}", "reuses_agent"))

    for grant in skill_grants:
        grant_node = f"skill_grant:{grant['id']}"
        nodes.append(_node(grant_node, "skill_grant", grant["skill_id"], grant["status"], version=grant["version"], granted_by=grant["granted_by"]))
        target = next((item for item in session_agents if item["agent_id"] == grant["agent_id"]), None)
        if target:
            edges.append(_edge(f"session_agent:{target['id']}", grant_node, "agent_uses_skill"))

    for grant in tool_grants:
        grant_node = f"tool_grant:{grant['id']}"
        nodes.append(_node(grant_node, "tool_grant", grant["tool_id"], grant["status"], granted_by=grant["granted_by"]))
        target = next((item for item in session_agents if item["agent_id"] == grant["agent_id"]), None)
        if target:
            edges.append(_edge(f"session_agent:{target['id']}", grant_node, "agent_allowed_tool"))

    for event in lifecycle_events:
        target = next((item for item in session_agents if item["agent_id"] == event["agent_id"]), None)
        if target and event["event_type"] in {"agent.retired", "delegation.approved", "delegation.rejected"}:
            event_node = f"lifecycle:{event['id']}"
            nodes.append(_node(event_node, "lifecycle_event", event["event_type"], "recorded", actor_id=event["actor_id"], payload=event.get("payload", {})))
            edges.append(_edge(f"session_agent:{target['id']}", event_node, "lifecycle_event"))

    return _dedupe(nodes, edges)


def team_graph(config_path: str | Path, team_id: str | None = None) -> dict:
    cfg = load_config(config_path)
    teams = [team for team in cfg.teams if team_id in (None, "", team.id)]
    agents = {agent.id: agent for agent in cfg.agents}
    nodes: list[dict] = []
    edges: list[dict] = []

    for team in teams:
        team_node = f"team:{team.id}"
        nodes.append(_node(team_node, "team", team.id, "configured", strategy=team.collaboration_strategy))
        if team.leader in agents:
            nodes.append(_agent_config_node(agents[team.leader]))
            edges.append(_edge(team_node, f"agent:{team.leader}", "has_leader", strategy=team.collaboration_strategy))
        for member_id in team.members:
            agent = agents.get(member_id)
            if not agent:
                continue
            nodes.append(_agent_config_node(agent))
            relation = "leader" if member_id == team.leader else "member"
            edges.append(_edge(team_node, f"agent:{member_id}", relation))
            if member_id != team.leader:
                edges.append(_edge(f"agent:{team.leader}", f"agent:{member_id}", "can_delegate", strategy=team.collaboration_strategy))
            for tool in agent.tools:
                nodes.append(_node(f"tool:{tool}", "tool", tool))
                edges.append(_edge(f"agent:{member_id}", f"tool:{tool}", "allowed_tool"))
            if agent.sandbox:
                nodes.append(_node(f"sandbox:{agent.sandbox}", "sandbox", agent.sandbox))
                edges.append(_edge(f"agent:{member_id}", f"sandbox:{agent.sandbox}", "runs_in"))
            for policy in agent.policies:
                nodes.append(_node(f"policy_config:{policy}", "policy", policy))
                edges.append(_edge(f"agent:{member_id}", f"policy_config:{policy}", "governed_by"))

    return _dedupe(nodes, edges)


def _agent_config_node(agent) -> dict:
    return _node(
        f"agent:{agent.id}",
        "agent",
        agent.name,
        "configured",
        provider=agent.provider,
        model=agent.model,
        tools=agent.tools,
        sandbox=agent.sandbox,
        policies=agent.policies,
    )


def _message_run_ids(message: dict, runs: list[dict], task_nodes: list[dict]) -> tuple[str | None, str | None]:
    run_ids = {run["id"] for run in runs}
    payload = message.get("payload") or {}
    message_type = message.get("message_type")

    if message_type == "leader.assignment":
        target = next(
            (
                node
                for node in task_nodes
                if node.get("plan_id") == payload.get("plan_id")
                and node.get("node_key") == payload.get("node_key")
                and node.get("run_id") in run_ids
            ),
            None,
        )
        source_id = message.get("trace_id")
        return (source_id if source_id in run_ids else None, target.get("run_id") if target else None)

    if message_type == "task.result":
        source_id = payload.get("child_run_id")
        target_id = message.get("parent_run_id") or message.get("trace_id")
        return (
            source_id if source_id in run_ids else None,
            target_id if target_id in run_ids else None,
        )

    if message_type == "task.assigned":
        source_id = message.get("parent_run_id") or message.get("trace_id")
        target = next(
            (
                run
                for run in reversed(runs)
                if run.get("parent_run_id") == source_id and run.get("agent_id") == message.get("target_agent_id")
            ),
            None,
        )
        return (source_id if source_id in run_ids else None, target.get("id") if target else None)

    return (None, None)


def _tool_call_for_step(tool_calls: list[dict], step_id: str | None) -> dict | None:
    if not step_id:
        return None
    return next((call for call in tool_calls if call.get("step_id") == step_id), None)


def _message_belongs_to_current(message: dict, run_ids: set[str], plan_id: str | None) -> bool:
    payload = message.get("payload") or {}
    if payload.get("plan_id"):
        return payload["plan_id"] == plan_id
    if payload.get("child_run_id"):
        return payload["child_run_id"] in run_ids
    return bool(message.get("trace_id") and message["trace_id"] in run_ids)
