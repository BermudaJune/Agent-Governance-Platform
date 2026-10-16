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
        if "天气" in task_input or "气温" in task_input:
            required.add("external.weather")
            networks.add("weather")
            risks.add("network")

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
        if any(word in task_input for word in ("故事", "写", "创作")):
            required.add("text.create")
            roles.add("writer")
        if any(word in task_input.lower() for word in ["image", "illustration", "配图", "图片", "插图", "绘图"]):
            required.add("visual.image_brief")
            artifacts.add("image")
            roles.add("designer")
        if any(word in task_input for word in ("配图", "图片", "插图", "绘图")):
            required.add("visual.image_brief")
            artifacts.add("image")
            roles.add("designer")
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

        if any(word in text for word in ["excel", "xlsx", "spreadsheet", "csv", "表格", "报表"]):
            required.update({"office.spreadsheet", "data.analysis"})
            artifacts.add("spreadsheet")
            roles.add("analyst")
        if any(word in text for word in ["ppt", "pptx", "powerpoint", "slide", "演示", "幻灯片"]):
            required.add("office.presentation")
            artifacts.add("presentation")
            roles.add("designer")
        if any(word in text for word in ["word", "docx", "document", "文档"]):
            required.add("office.document")
            artifacts.add("document")
        if any(word in text for word in ["pdf", "报告"]):
            required.add("office.pdf")
            artifacts.add("pdf")
        if any(word in text for word in ["chart", "图表", "柱状图", "折线图", "趋势图"]):
            required.add("visual.chart")
            artifacts.add("chart")
        if any(word in text for word in ["mermaid", "diagram", "架构图", "流程图", "拓扑图"]):
            required.add("visual.diagram")
            artifacts.add("diagram")

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
