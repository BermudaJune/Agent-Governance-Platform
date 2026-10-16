from __future__ import annotations

from agentgov.config.schema import PlatformConfig
from agentgov.planning.models import TaskNodeSpec


class RuleBasedSessionPlanner:
    def __init__(self, cfg: PlatformConfig | None = None):
        self.cfg = cfg
        self._agents = {agent.id: agent for agent in cfg.agents} if cfg else {}

    def plan(self, *, objective: str, strategy: str, leader: str, members: list[str]) -> list[TaskNodeSpec]:
        agent_ids = list(dict.fromkeys([leader, *members]))
        if strategy == "planner_executor_reviewer":
            return self._plan_governance_review(objective, agent_ids)
        if strategy == "sequential_artifact_review" or self._looks_like_artifact_review(objective, agent_ids):
            return self._plan_artifact_review(objective, agent_ids)
        return self._plan_leader_worker(objective, strategy, leader, agent_ids)

    def _plan_artifact_review(self, objective: str, agent_ids: list[str]) -> list[TaskNodeSpec]:
        weather = self._find_agent(agent_ids, kind="weather")
        writer = self._find_agent(agent_ids, kind="writer") or agent_ids[0]
        illustrator = self._find_designer(agent_ids) or writer
        reviewer = self._find_agent(agent_ids, kind="reviewer")
        nodes: list[TaskNodeSpec] = []
        if any(keyword in objective for keyword in ("天气", "气温")):
            needs_weather_override = True
        else:
            needs_weather_override = False

        needs_weather = any(keyword in objective.lower() for keyword in ("weather", "forecast")) or "天气" in objective
        if weather and (needs_weather or needs_weather_override):
            nodes.append(
                TaskNodeSpec(
                    node_key="weather",
                    assigned_agent_id=weather,
                    title="Collect weather context",
                    instruction=(
                        "Query or summarize the weather facts required by the user task. "
                        f"User objective: {objective}"
                    ),
                    required_capabilities=["external.weather"],
                    required_tools=["weather_lookup"],
                    output_contract={"weather_summary": "facts usable by downstream writing nodes"},
                )
            )

        writer_depends = ["weather"] if any(node.node_key == "weather" for node in nodes) else []
        nodes.append(
            TaskNodeSpec(
                node_key="write_artifact",
                assigned_agent_id=writer,
                title="Write primary artifact",
                instruction=(
                    "Create the requested text artifact. If upstream context exists, use it as factual input. "
                    "Write the main output to story.md unless the user explicitly requested another relative filename. "
                    f"User objective: {objective}"
                ),
                required_capabilities=["text.create", "file.write"],
                required_tools=["file_write"],
                depends_on=writer_depends,
                input_refs=writer_depends,
                output_contract={"artifact": "story.md or requested primary text file"},
            )
        )

        needs_illustration = any(keyword in objective.lower() for keyword in ("image", "illustration")) or any(keyword in objective for keyword in ("配图", "图片", "插图", "绘图"))
        if needs_illustration or any(keyword in objective for keyword in ("配图", "图片", "插图", "绘图")):
            nodes.append(
                TaskNodeSpec(
                    node_key="illustrate_artifact",
                    assigned_agent_id=illustrator,
                    title="Generate story illustration",
                    instruction=(
                        "Generate a PNG illustration for the story using the image_generate tool. "
                        "Use upstream weather and story context; save it as artifacts/story-illustration.png. "
                        f"User objective: {objective}"
                    ),
                    required_tools=["image_generate"],
                    depends_on=["write_artifact"],
                    input_refs=["write_artifact"],
                    output_contract={"artifact": "artifacts/story-illustration.png"},
                )
            )

        if reviewer and reviewer != writer:
            nodes.append(
                TaskNodeSpec(
                    node_key="review_artifact",
                    assigned_agent_id=reviewer,
                    title="Review primary artifact",
                    instruction=(
                        "Review the upstream artifact and write a review file. "
                        "Read story.md when available, then write review.md unless another relative filename is requested. "
                        f"User objective: {objective}"
                    ),
                    required_capabilities=["file.read", "review.content", "file.write"],
                    required_tools=["file_read", "file_write"],
                    depends_on=["write_artifact"],
                    input_refs=["write_artifact"],
                    output_contract={"artifact": "review.md or requested review file"},
                )
            )
        return nodes

    def _plan_governance_review(self, objective: str, agent_ids: list[str]) -> list[TaskNodeSpec]:
        leader = agent_ids[0]
        nodes: list[TaskNodeSpec] = [
            TaskNodeSpec(
                node_key="plan",
                assigned_agent_id=leader,
                title="Plan governance review",
                instruction=f"Plan the governance review and define evidence, execution, policy and final review expectations. User objective: {objective}",
                required_capabilities=["coordination.plan", "coordination.delegate"],
                output_contract={"plan": "governance review task plan"},
            )
        ]
        order = [
            ("evidence", "Collect evidence", "Collect repository or context evidence for the task.", ["plan"]),
            ("execution", "Run readonly checks", "Run safe readonly checks if needed and report outputs.", ["plan", "evidence"]),
            ("policy_auditor", "Audit policy", "Review permission, budget, HITL and audit trail risks.", ["plan", "evidence"]),
            ("reviewer", "Final review", "Synthesize upstream evidence, execution and policy findings.", ["plan", "evidence", "execution", "policy_auditor"]),
        ]
        for key, title, instruction, deps in order:
            if key in agent_ids:
                nodes.append(
                    TaskNodeSpec(
                        node_key=key,
                        assigned_agent_id=key,
                        title=title,
                        instruction=f"{instruction} User objective: {objective}",
                        depends_on=[dep for dep in deps if dep == "plan" or dep in agent_ids],
                        input_refs=[dep for dep in deps if dep == "plan" or dep in agent_ids],
                    )
                )
        if len(nodes) > 1:
            return nodes
        return self._plan_leader_worker(objective, "planner_executor_reviewer", agent_ids[0], agent_ids)

    def _plan_leader_worker(self, objective: str, strategy: str, leader: str, agent_ids: list[str]) -> list[TaskNodeSpec]:
        nodes = [
            TaskNodeSpec(
                node_key="plan",
                assigned_agent_id=leader,
                title="Plan and coordinate",
                instruction=f"Create a concise plan for the team and define what each worker should produce. User objective: {objective}",
                required_capabilities=["coordination.plan", "coordination.delegate"],
                output_contract={"plan": "worker instructions and acceptance notes"},
            )
        ]
        for agent_id in [item for item in agent_ids if item != leader]:
            nodes.append(
                TaskNodeSpec(
                    node_key=f"work_{agent_id}",
                    assigned_agent_id=agent_id,
                    title=f"Worker task for {agent_id}",
                    instruction=f"Complete your assigned part under {strategy}. User objective: {objective}",
                    depends_on=["plan"],
                    input_refs=["plan"],
                    output_contract={"summary": "worker result"},
                )
            )
        return nodes

    def _find_agent(self, agent_ids: list[str], *, kind: str) -> str | None:
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            tools = set(agent.tools if agent else [])
            capabilities = set(agent.capabilities if agent else [])
            text = f"{agent_id} {agent.name if agent else ''}".lower()
            if kind == "weather" and ("weather_lookup" in tools or "external.weather" in capabilities or "weather" in text or "天气" in text):
                return agent_id
            if kind == "writer" and ("file_write" in tools or "text.create" in capabilities or "writer" in text or "写" in text):
                if "review" not in text and "评价" not in text:
                    return agent_id
            if kind == "reviewer" and ("review.content" in capabilities or "file_read" in tools or "review" in text or "评价" in text):
                return agent_id
        return None

    def _find_designer(self, agent_ids: list[str]) -> str | None:
        for agent_id in agent_ids:
            agent = self._agents.get(agent_id)
            if agent and ("image_generate" in agent.tools or "visual.image_brief" in agent.capabilities):
                return agent_id
        return None

    def _looks_like_artifact_review(self, objective: str, agent_ids: list[str]) -> bool:
        has_writer = self._find_agent(agent_ids, kind="writer") is not None
        has_reviewer = self._find_agent(agent_ids, kind="reviewer") is not None
        objective_text = objective.lower()
        wants_artifact = any(keyword in objective_text for keyword in ("write", "story", "poem", "file")) or any(
            keyword in objective for keyword in ("写", "故事", "诗", "文件", "评价", "鉴赏")
        )
        has_weather = self._find_agent(agent_ids, kind="weather") is not None
        wants_illustration = any(keyword in objective_text for keyword in ("image", "illustration")) or any(keyword in objective for keyword in ("配图", "图片", "插图", "绘图"))
        wants_artifact = wants_artifact or any(keyword in objective for keyword in ("写", "故事", "文件", "配图"))
        wants_illustration = wants_illustration or any(keyword in objective for keyword in ("配图", "图片", "插图", "绘图"))
        return has_writer and (has_reviewer or has_weather or wants_illustration) and wants_artifact
