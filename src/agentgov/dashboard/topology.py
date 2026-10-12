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


def session_graph(repo: Repository, session_id: str) -> dict:
    session = repo.get_session(session_id)
    runs = repo.list_runs_for_session(session_id)
    steps = repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,))
    messages = repo.query_all("agent_messages", "WHERE session_id = ? ORDER BY created_at", (session_id,))
    model_calls = repo.query_all("model_calls", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,))
    tool_calls = repo.query_all("tool_calls", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,))
    evidence_refs = repo.query_all("evidence_refs", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,))
    approvals = repo.query_all("approvals", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,))
    policies = repo.query_all("policy_decisions", "WHERE run_id IN (SELECT id FROM runs WHERE session_id = ?)", (session_id,))

    nodes: list[dict] = []
    edges: list[dict] = []
    task_id = f"session:{session_id}"
    nodes.append(_node(task_id, "session", session["title"] if session else session_id, session["status"] if session else None))

    for run in runs:
        run_id = f"run:{run['id']}"
        nodes.append(_node(run_id, "run", run["agent_id"], run["status"], input=run["input_summary"], error=run.get("error")))
        if run.get("parent_run_id"):
            edges.append(_edge(f"run:{run['parent_run_id']}", run_id, "delegates_to", agent_id=run["agent_id"]))
        else:
            edges.append(_edge(task_id, run_id, "starts", agent_id=run["agent_id"]))

    for message in messages:
        source_run = _latest_run_for_agent(runs, message["source_agent_id"])
        target_run = _latest_run_for_agent(runs, message["target_agent_id"])
        if source_run and target_run:
            edges.append(
                _edge(
                    f"run:{source_run['id']}",
                    f"run:{target_run['id']}",
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


def _latest_run_for_agent(runs: list[dict], agent_id: str) -> dict | None:
    matches = [run for run in runs if run["agent_id"] == agent_id]
    return matches[-1] if matches else None


def _tool_call_for_step(tool_calls: list[dict], step_id: str | None) -> dict | None:
    if not step_id:
        return None
    return next((call for call in tool_calls if call.get("step_id") == step_id), None)
