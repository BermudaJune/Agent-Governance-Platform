from __future__ import annotations

import re

from agentgov.capabilities.models import TaskRequirement


class RequirementAnalyzer:
    def analyze(self, task_input: str, *, use_llm: bool = False) -> TaskRequirement:
        text = task_input.lower()
        required: set[str] = set()
        roles: set[str] = {"coordinator"}
        artifacts: set[str] = set()
        risks: set[str] = set()
        paths = re.findall(r"[a-zA-Z]:\\[^\s，。；,;]+", task_input)
        networks: set[str] = set()

        if any(word in text for word in ["weather", "天气", "气温", "forecast"]):
            required.add("external.weather")
            networks.add("weather")
            risks.add("network")
        if any(word in text for word in ["write", "save", "保存", "写入", "写到", "文件", ".md", ".txt"]):
            required.add("file.write")
            artifacts.add("file")
            risks.add("write")
        if any(word in text for word in ["read", "读取", "阅读", "鉴赏", "评价", "review"]):
            required.add("file.read")
        if any(word in text for word in ["poem", "诗", "创作", "故事", "文案"]):
            required.add("text.create")
            roles.add("writer")
        if any(word in text for word in ["鉴赏", "评价", "评审", "review", "审查"]):
            required.add("review.content")
            roles.add("reviewer")
        if any(word in text for word in ["仓库", "代码", "repo", "repository", "源码"]):
            required.update({"repo.list", "repo.search", "repo.read"})
            roles.add("researcher")
        if any(word in text for word in ["命令", "测试", "运行", "pytest", "npm", "command"]):
            required.add("command.local_readonly")
            roles.add("executor")
            risks.add("command")
        if any(word in text for word in ["策略", "权限", "审计", "预算", "hitl", "policy"]):
            required.add("review.policy")
            roles.add("auditor")

        if len(roles) > 1:
            required.add("coordination.plan")
            required.add("coordination.delegate")

        return TaskRequirement(
            task_summary=task_input,
            required_capabilities=sorted(required),
            required_roles=sorted(roles),
            expected_artifacts=sorted(artifacts),
            risk_hints=sorted(risks),
            path_requirements=paths,
            network_requirements=sorted(networks),
        )
