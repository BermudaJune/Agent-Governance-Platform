from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from threading import Lock

from pydantic import BaseModel, Field

from agentgov.config.loader import load_config
from agentgov.planning.models import TaskNodeSpec
from agentgov.runtime.dynamic_governance import DynamicGovernanceService
from agentgov.skills.catalog import search_github_skill_repositories
from agentgov.storage.models import now_iso


class CapabilityAlternative(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    proposal: str = Field(min_length=1, max_length=1200)
    tradeoff: str = Field(min_length=1, max_length=600)
    prerequisites: list[str] = Field(default_factory=list, max_length=6)


class CapabilityGap(BaseModel):
    capability: str
    reason: str
    search_query: str = ""
    alternatives: list[CapabilityAlternative] = Field(default_factory=list, max_length=3)


class LeaderProposal(BaseModel):
    understanding: str = Field(min_length=1)
    reply: str = Field(min_length=1)
    questions: list[str] = Field(default_factory=list, max_length=6)
    acceptance: list[str] = Field(default_factory=list, max_length=12)
    nodes: list[TaskNodeSpec] = Field(default_factory=list, max_length=24)
    preserve_node_keys: list[str] = Field(default_factory=list)
    capability_gaps: list[CapabilityGap] = Field(default_factory=list, max_length=6)
    skills_by_agent: dict[str, list[str]] = Field(default_factory=dict)


class LeaderWorkflowService:
    """Persist user intent before calling the model; publish only validated plans."""

    def __init__(self, runs, config_path: str):
        self.runs = runs
        self.repo = runs.repo
        self.config_path = config_path
        self.governance = DynamicGovernanceService(self.repo, config_path)
        self._locks: dict[str, Lock] = {}
        self._locks_guard = Lock()

    def is_managed(self, session_id: str) -> bool:
        return bool((self.repo.get_session(session_id) or {}).get("metadata", {}).get("leader"))

    def state(self, session_id: str) -> dict:
        state = dict((self.repo.get_session(session_id) or {}).get("metadata", {}).get("leader") or {})
        if state:
            state["pending_requests"] = [r for r in self.repo.list_delegation_requests(session_id) if r["status"] == "pending"]
        return state

    def readiness(self, session_id: str, node: dict | None = None) -> str | None:
        state = self.state(session_id)
        if state.get("status") in {"planning", "planning_failed"} or state.get("questions") or state.get("unresolved_gaps"):
            return "Leader 规划、需求澄清或能力缺口尚未解决"
        active = {a["agent_id"] for a in self.repo.list_session_agents(session_id) if a["status"] == "active"}
        for item in ([node] if node else [n for n in self.repo.list_task_nodes_for_session(session_id) if n["status"] not in {"superseded", "completed"}]):
            agent = item["assigned_agent_id"]
            if agent not in active:
                return f"Agent {agent} 尚未获准加入 Session"
            allowed = {t["function"]["name"] for t in self.runs.loop.tool_gateway.schemas_for_agent(agent, session_id)}
            if set(item.get("required_tools", [])) - allowed:
                return f"Agent {agent} 的工具授权尚未完成"
            cfg_agent = next((a for a in load_config(self.config_path).agents if a.id == agent), None)
            skills = set(cfg_agent.skills if cfg_agent else []) | {g["skill_id"] for g in self.repo.list_session_skill_grants(session_id) if g["agent_id"] == agent and g["status"] == "active"}
            if set(state.get("skills_by_agent", {}).get(agent, [])) - skills:
                return f"Agent {agent} 的 Skill 授权尚未完成"
        return None

    def _state(self, session_id: str, **changes) -> dict:
        session = self.repo.get_session(session_id)
        metadata = dict(session.get("metadata") or {})
        state = {**metadata.get("leader", {}), **changes, "updated_at": now_iso()}
        self.repo.update_generic("sessions", session_id, {"metadata": {**metadata, "leader": state}, "updated_at": now_iso()})
        return state

    def _message(self, session_id: str, source: str, target: str, kind: str, text: str, **payload):
        state = self.state(session_id)
        self.repo.insert_generic("agent_messages", {
            "session_id": session_id, "trace_id": state.get("planning_run_id"),
            "source_agent_id": source, "target_agent_id": target, "message_type": kind,
            "payload": {"content": text, **payload}, "status": "sent", "created_at": now_iso(),
        })

    def dispatch(self, req) -> dict:
        session = self.runs.create_session(
            req.title, req.owner_id, req.leader_id, objective=req.input_summary,
            knowledge_sources=[s.model_dump() for s in req.knowledge_sources],
            knowledge_policy=req.knowledge_policy.model_dump(),
        )
        anchor = self.runs.create_run(session.id, req.leader_id, req.input_summary)
        self.repo.update_generic("runs", anchor.id, {"run_type": "leader_planning"})
        self._state(session.id, status="planning", planning_run_id=anchor.id,
                    requested_skills=req.requested_skills, requested_tools=req.requested_tools)
        self.governance.ensure_root(session.id)
        self._message(session.id, req.owner_id, req.leader_id, "leader.user", req.input_summary)
        return self.plan(session.id)

    def message(self, session_id: str, **feedback) -> dict:
        session = self.repo.get_session(session_id)
        if not session:
            raise KeyError(session_id)
        # Serialize intent updates with plan publication, while pause/cancel remain available.
        with self._lock(session_id):
            result = self.runs.submit_session_feedback(session_id, **feedback)
            self._message(session_id, feedback.get("created_by", "operator"), session["root_agent_id"],
                          "leader.user", feedback["message"], feedback_id=result["feedback"]["id"],
                          requirement_id=result["requirement"]["id"], feedback_target=result["impact"]["target"])
        return {**self.plan(session_id), "impact": result["impact"]}

    def _lock(self, session_id: str):
        with self._locks_guard:
            return self._locks.setdefault(session_id, Lock())

    @staticmethod
    def validate(proposal: LeaderProposal, known_agents: set[str]) -> None:
        nodes = {n.node_key: n for n in proposal.nodes}
        if len(nodes) != len(proposal.nodes) or any(not key.strip() for key in nodes):
            raise ValueError("node_key must be unique and nonempty")
        if not nodes and not (proposal.questions or proposal.capability_gaps):
            raise ValueError("plan needs executable nodes or explicit questions/capability gaps")
        for node in proposal.nodes:
            if node.assigned_agent_id not in known_agents:
                raise ValueError(f"unknown agent: {node.assigned_agent_id}; select a configured agent")
            if not node.title.strip() or not node.instruction.strip():
                raise ValueError("node title and instruction must not be empty")
            if set(node.depends_on) - set(nodes):
                raise ValueError(f"unknown dependency in {node.node_key}")
            files = node.output_contract.get("files", [])
            if not isinstance(files, list) or any(not isinstance(f, str) or not f.strip() or PureWindowsPath(f).is_absolute() or PurePosixPath(f).is_absolute() or ".." in PureWindowsPath(f).parts for f in files):
                raise ValueError("output_contract.files must contain safe relative paths")
        visited, visiting = set(), set()

        def visit(key):
            if key in visiting:
                raise ValueError("task graph contains a cycle")
            if key in visited:
                return
            visiting.add(key)
            for dependency in nodes[key].depends_on:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in nodes:
            visit(key)
        if set(proposal.preserve_node_keys) - set(nodes):
            raise ValueError("preserved nodes must appear in the desired graph")
        if set(proposal.skills_by_agent) - known_agents:
            raise ValueError("unknown agent in skill assignments")

    def plan(self, session_id: str) -> dict:
        if not self._lock(session_id).acquire(blocking=False):
            return {"session_id": session_id, "status": "planning", "leader": self.state(session_id)}
        try:
            return self._plan(session_id)
        finally:
            self._lock(session_id).release()

    def _plan(self, session_id: str) -> dict:
        session = self.repo.get_session(session_id)
        requirement = self.repo.get_current_requirement(session_id)
        if not session or not requirement:
            raise KeyError(session_id)
        state = self.state(session_id)
        run_id, leader = state["planning_run_id"], session["root_agent_id"]
        if session["status"] in {"cancelled", "paused"}:
            return {"session_id": session_id, "status": session["status"], "leader": state}
        self._state(session_id, status="planning", error="", questions=[], unresolved_gaps=[])
        self.repo.update_session_status(session_id, "replanning", "Leader 正在分析需求与可用能力")
        self.repo.update_run_status(run_id, "running")
        try:
            cfg = load_config(self.config_path)
            old_nodes = [n for n in self.repo.list_task_nodes_for_session(session_id) if n["status"] != "superseded"]
            tools = self.runs.loop.tool_gateway.registry.list_specs()
            prompt = (
                "你是负责完成用户任务的 Leader。分析需求，必要时澄清，规划完整的目标 DAG。只输出 JSON，不执行任务。"
                "任务可以多步骤并行、评价后修改、最终交付。不要固定套模板；简单任务不要硬拆成多 Agent。"
                "用户反馈必须改变不合适的步骤、指令、工具或依赖。保留明确不受影响且已完成的节点时保持原 node_key 和全部规格。"
                "只能选择给出的 Agent ID。Skill 是方法说明，不代表工具/模型已具备。需要联网事实必须用相应工具，缺城市等关键参数先问。"
                "工具不在清单、图像供应商未配置、所需依赖不可用等必须列 capability_gaps，提出搜索关键词或替代方案。"
                "当前 image_generate 只是 matplotlib 固定天气示意图，不具备人物、动漫或任意场景的生成能力；此类请求必须报缺口。"
                "不能声称已搜索、已下载或已生成。skills_by_agent 只选已安装 Skill ID；工具授权由平台审批，不可跳过。"
                "必填字段 understanding、reply；questions 为需要用户回答的问题；acceptance 为验收标准；nodes 是完整任务图。"
                "每节点含 node_key,assigned_agent_id,title,instruction,depends_on,required_tools,output_contract。"
                "output_contract 的 files 如存在，是必须真实生成的相对文件路径列表。节点只产出文本时不用 files。"
                "preserve_node_keys 是希望复用的已完成节点；capability_gaps 每项含 capability,reason,search_query,alternatives；"
                "缺口的 alternatives 给出最多三条针对当前任务的候选路线，每项含 title、proposal、tradeoff、prerequisites。"
                "说明交付要求会如何改变、需要用户提供什么或配置哪些执行器。不要假设候选服务已可用，不擅自降低要求。"
                "只有用户明确选择并重新审批后才采用替代路线；如果无法给出可靠替代，就保持缺口并明确前置条件。"
                "skills_by_agent 为 {agent_id:[skill_id]}。用中文沟通，搜索词可用英文。\n"
                + json.dumps({"requirement": requirement, "agents": [a.model_dump(mode="json") for a in cfg.agents],
                              "installed_skills": [s.model_dump(mode="json", exclude={"prompt_body"}) for s in cfg.skills],
                              "runtime_tools": [t.model_dump(mode="json") for t in tools],
                              "previous_nodes": old_nodes, "previous_edges": self.repo.list_task_edges_for_session(session_id),
                              "artifacts": self.repo.list_artifacts_for_session(session_id),
                              "requested_skills": state.get("requested_skills", []), "requested_tools": state.get("requested_tools", [])}, ensure_ascii=False)
            )
            proposal = None
            for attempt in range(2):
                response = self.runs.loop.model_gateway.complete(run_id, session_id, leader, prompt, tools=[])
                try:
                    content = response.content.strip()
                    if content.startswith("```"):
                        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                    proposal = LeaderProposal.model_validate(json.loads(content))
                    self.validate(proposal, {a.id for a in cfg.agents})
                    break
                except (ValueError, TypeError) as exc:
                    if attempt:
                        raise
                    self.runs.events.append(run_id, session_id, "leader.plan.validation_failed", "leader", leader, "retrying", {"error": str(exc)[:2000]})
                    prompt += "\n上次输出未通过校验，请修复并返回完整 JSON：" + str(exc)[:2000] + "\n" + response.content[:12000]
            current_session = self.repo.get_session(session_id)
            if current_session["status"] in {"paused", "cancelled"}:
                self.repo.update_run_status(run_id, current_session["status"])
                self._state(session_id, status=current_session["status"])
                return {"session_id": session_id, "status": current_session["status"]}
            if self.repo.get_current_requirement(session_id)["id"] != requirement["id"]:
                raise ValueError("需求已变化，本次规划未发布，请重试")
            result = self._publish(session_id, requirement, proposal, old_nodes, cfg)
            self.repo.update_run_status(run_id, "completed", output_summary=proposal.reply)
            return {**result, "parent_run_id": run_id, "leader": self.state(session_id)}
        except Exception as exc:
            error = str(exc)[:2000]
            self.repo.update_run_status(run_id, "failed", error=error)
            self.repo.update_session_status(session_id, "needs_replan", "Leader 规划未完成，可重试；需求与反馈已保留")
            self._state(session_id, status="planning_failed", error=error)
            self._message(session_id, leader, "operator", "leader.error", "本次规划未完成。需求和反馈已保存，可重试。", error=error)
            return {"session_id": session_id, "parent_run_id": run_id, "status": "planning_failed", "leader": self.state(session_id)}

    def _publish(self, session_id, requirement, proposal, old_nodes, cfg):
        leader = self.repo.get_session(session_id)["root_agent_id"]
        state = self.state(session_id)
        gaps = [g.model_dump() for g in proposal.capability_gaps]
        known_tools = {t.id for t in self.runs.loop.tool_gateway.registry.list_specs()}
        known_skills = {s.id for s in cfg.skills}
        for tool in sorted({t for n in proposal.nodes for t in n.required_tools} - known_tools):
            gaps.append({"capability": tool, "reason": "运行时没有此工具；导入 Skill 不会自动安装执行器", "search_query": tool + " agent skill"})
        for skill in sorted({s for ids in proposal.skills_by_agent.values() for s in ids} - known_skills):
            gaps.append({"capability": skill, "reason": "Skill 尚未安装", "search_query": skill})
        for gap in gaps:
            if not gap.get("alternatives"):
                gap["alternatives"] = [
                    {"title": "由我提供资料或已有成果",
                     "proposal": f"针对缺口「{gap['capability']}」，先向我确认需要哪些资料或已有成果，再评估可否完成任务。",
                     "tradeoff": "依赖用户提供资料；在资料验证前仍保持阻塞，不保证能够替代原能力。",
                     "prerequisites": ["Leader 明确输入格式与验收条件", "用户提供资料并确认其适用性"]},
                    {"title": "先明确接入条件，保留原要求",
                     "proposal": f"保留当前任务要求，列明补齐「{gap['capability']}」需要的执行器、服务配置及权限，等待配置后重新检查。",
                     "tradeoff": "需要接入并验证实际执行能力，单独导入 Skill 不能消除此缺口。",
                     "prerequisites": [gap["reason"], "运行时及依赖验证通过", "获得 Session 所需授权"]},
                ]
        previous = self.repo.get_plan_for_session(session_id)
        old_by_key = {n["node_key"]: n for n in old_nodes}
        preserved = {}
        # Reuse only unchanged completed evidence, including its dependency graph.
        for spec in proposal.nodes:
            old = old_by_key.get(spec.node_key)
            completed = (old and old["status"] in {"completed", "stale"}
                         and (self.repo.get_run(old["run_id"]) or {}).get("status") == "completed"
                         and self._preserved_outputs_exist(session_id, old))
            if spec.node_key not in proposal.preserve_node_keys or not completed:
                continue
            deps = [old_node["node_key"] for edge in self.repo.list_task_edges_for_session(session_id)
                    if edge["target_node_id"] == old["id"] for old_node in old_nodes if old_node["id"] == edge["source_node_id"]]
            fields = ("assigned_agent_id", "instruction", "required_tools", "output_contract", "input_refs")
            if all(getattr(spec, key) == old.get(key, [] if key in {"required_tools", "input_refs"} else {}) for key in fields) and set(spec.depends_on) == set(deps):
                preserved[spec.node_key] = old
        changed = True
        while changed:
            changed = False
            for spec in proposal.nodes:
                if spec.node_key in preserved and any(dep not in preserved for dep in spec.depends_on):
                    del preserved[spec.node_key]
                    changed = True
        for old in preserved.values():
            self.repo.update_generic("task_nodes", old["id"], {"status": "completed", "updated_at": now_iso()})
            for artifact in self.repo.list_artifacts_for_session(session_id):
                if artifact.get("run_id") == old["run_id"]:
                    self.repo.update_generic("artifacts", artifact["id"], {"metadata": {**artifact.get("metadata", {}), "stale": False}})
                    for version in self.repo.query_all("artifact_versions", "WHERE artifact_id = ?", (artifact["id"],)):
                        self.repo.update_generic("artifact_versions", version["id"], {"status": "active"})
        specs = [n.model_copy(update={"depends_on": [d for d in n.depends_on if d not in preserved]})
                 for n in proposal.nodes if n.node_key not in preserved]
        run_ids = {n.node_key: self.runs.create_run(session_id, n.assigned_agent_id, n.instruction,
                   parent_run_id=state["planning_run_id"]).id for n in specs}
        self.runs.planning.create_plan(
            session_id=session_id, objective=requirement["objective"], strategy="leader_workflow", planner_agent_id=leader,
            nodes=specs, run_ids_by_node_key=run_ids, requirement_id=requirement["id"],
            parent_plan_id=(previous or {}).get("id"), change_reason=proposal.reply, approval_status="required")
        plan = self.repo.get_plan_for_session(session_id)
        new_nodes = {n["node_key"]: n for n in self.repo.list_task_nodes_for_plan(plan["id"])}
        for spec in proposal.nodes:
            if spec.node_key in preserved:
                continue
            for dep in spec.depends_on:
                if dep in preserved:
                    self.repo.insert_generic("task_edges", {"plan_id": plan["id"], "source_node_id": preserved[dep]["id"],
                        "target_node_id": new_nodes[spec.node_key]["id"], "edge_type": "depends_on", "payload_key": dep, "created_at": now_iso()})
            self._message(session_id, leader, spec.assigned_agent_id, "leader.assignment", spec.instruction, node_key=spec.node_key, plan_id=plan["id"])
        for old in old_nodes:
            if old["node_key"] not in preserved:
                self.repo.update_generic("task_nodes", old["id"], {"status": "superseded", "updated_at": now_iso()})
        if previous:
            self.repo.update_generic("session_plans", previous["id"], {"status": "superseded", "updated_at": now_iso()})
        diff = {"added": [n.node_key for n in proposal.nodes if n.node_key not in old_by_key],
                "revised": [n.node_key for n in proposal.nodes if n.node_key in old_by_key and n.node_key not in preserved],
                "preserved": list(preserved), "removed": [key for key in old_by_key if key not in {n.node_key for n in proposal.nodes}]}
        self.repo.update_generic("session_plans", plan["id"], {"status": "awaiting_approval", "raw_plan": {**proposal.model_dump(), "diff": diff}, "updated_at": now_iso()})
        for feedback in self.repo.list_session_feedback(session_id):
            if feedback["status"] == "needs_replan":
                self.repo.update_generic("session_feedback", feedback["id"], {"status": "planned"})
        self._state(session_id, status="needs_clarification" if proposal.questions else "capability_gap" if gaps else "awaiting_approval",
                    understanding=proposal.understanding, reply=proposal.reply, questions=proposal.questions,
                    acceptance=proposal.acceptance, unresolved_gaps=gaps, diff=diff, error="", discovery=[], skills_by_agent=proposal.skills_by_agent)
        for request in self.repo.list_delegation_requests(session_id):
            if request["status"] == "pending":
                self.repo.update_generic("delegation_requests", request["id"], {"status": "superseded", "decided_at": now_iso()})
                if request.get("approval_id"):
                    self.repo.update_generic("approvals", request["approval_id"], {"status": "superseded", "reason": "Leader 已发布新版本计划", "decided_at": now_iso()})
        self._request_capabilities(session_id, proposal, cfg)
        session_status = "blocked" if proposal.questions or gaps else "awaiting_approval"
        summary = proposal.understanding
        if proposal.questions:
            summary = "等待需求澄清：" + proposal.questions[0]
        elif gaps:
            summary = "能力缺口待解决：" + "、".join(g["capability"] for g in gaps)
        self.repo.update_session_status(session_id, session_status, summary)
        self._message(session_id, leader, "operator", "leader.reply", proposal.reply, requirement_id=requirement["id"], plan_id=plan["id"], diff=diff)
        self.runs.events.append(state["planning_run_id"], session_id, "leader.plan.published", "leader", leader, "awaiting_approval", {"plan_id": plan["id"], "requirement_id": requirement["id"], "diff": diff, "gaps": gaps})
        if gaps:
            self.discover(session_id)
        return {"session_id": session_id, "status": self.state(session_id)["status"], "plan": self.runs.planning.get_plan_bundle(session_id)}

    def _preserved_outputs_exist(self, session_id: str, node: dict) -> bool:
        expected = (node.get("output_contract") or {}).get("files", [])
        if not isinstance(expected, list) or not expected:
            return True
        workspace = (self.runs.loop.tool_gateway.registry.repo_tools.root / "data" / "workspaces" / session_id).resolve()
        recorded = {
            Path(artifact["path"]).resolve()
            for artifact in self.repo.list_artifacts_for_session(session_id)
            if artifact.get("run_id") == node.get("run_id")
        }
        for name in expected:
            target = (workspace / str(name)).resolve()
            if workspace not in target.parents or target not in recorded or not target.is_file():
                return False
        return True

    def _request_capabilities(self, session_id, proposal, cfg):
        state = self.state(session_id)
        leader = self.repo.get_session(session_id)["root_agent_id"]
        active = {a["agent_id"] for a in self.repo.list_session_agents(session_id) if a["status"] == "active"}
        agents = {a.id: a for a in cfg.agents}
        desired = {n.assigned_agent_id for n in proposal.nodes} | set(proposal.skills_by_agent)
        if state.get("requested_tools") or state.get("requested_skills"):
            desired.add(leader)
        for agent_id in desired:
            agent = agents[agent_id]
            tools = {t for n in proposal.nodes if n.assigned_agent_id == agent_id for t in n.required_tools}
            skills = set(proposal.skills_by_agent.get(agent_id, []))
            if agent_id == leader:
                tools.update(state.get("requested_tools", []))
                skills.update(state.get("requested_skills", []))
            allowed_tools = {s["function"]["name"] for s in self.runs.loop.tool_gateway.schemas_for_agent(agent_id, session_id)}
            allowed_skills = set(agent.skills) | {s["skill_id"] for s in self.repo.list_session_skill_grants(session_id) if s["agent_id"] == agent_id and s["status"] == "active"}
            tools = (tools - allowed_tools) & {t.id for t in self.runs.loop.tool_gateway.registry.list_specs()}
            skills = (skills - allowed_skills) & {s.id for s in cfg.skills}
            if tools or skills or agent_id not in active:
                self.governance.create_delegation(session_id, {"parent_agent_id": leader, "requested_agent_id": agent_id,
                    "run_id": state["planning_run_id"], "objective": "Leader 计划所需的成员与能力", "requested_role": "specialist",
                    "requested_skills": sorted(skills), "requested_tools": sorted(tools), "auto_approve": False})

    def discover(self, session_id: str) -> dict:
        state = self.state(session_id)
        results = []
        for index, gap in enumerate(state.get("unresolved_gaps", [])):
            query = gap.get("search_query") or gap["capability"]
            if index >= 2:
                results.append({"query": query, "capability": gap["capability"], "status": "not_searched",
                                "reason": "每轮最多自动搜索两个缺口；可手动搜索或与 Leader 选择其他路线", "repositories": []})
                continue
            try:
                repos = search_github_skill_repositories(query, 4)
                results.append({"query": query, "capability": gap["capability"], "status": "found" if repos else "no_results", "repositories": repos})
            except Exception as exc:
                results.append({"query": query, "capability": gap["capability"], "status": "failed", "error": str(exc)[:1000], "repositories": []})
        self._state(session_id, discovery=results)
        self.runs.events.append(state["planning_run_id"], session_id, "leader.skills.searched", "leader", "leader", "completed", {"results": results, "executes_code": False})
        return {"session_id": session_id, "results": results}
