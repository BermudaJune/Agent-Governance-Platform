from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from agentgov.config.schema import PlatformConfig, ToolConfig
from agentgov.providers.local_repo_tools import LocalRepoTools
from agentgov.sandbox.service import SandboxService


class ToolSpec(BaseModel):
    id: str
    name: str
    description: str
    category: str = "read"
    executor: str = "builtin"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    sandbox: str | None = None
    requires_approval: bool = False
    is_concurrency_safe: bool = False
    should_defer: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)

    def openai_tool(self) -> dict[str, Any]:
        parameters = self.input_schema or {"type": "object", "properties": {}, "additionalProperties": False}
        return {
            "type": "function",
            "function": {
                "name": self.id,
                "description": self.description,
                "parameters": parameters,
            },
        }


@dataclass
class ToolExecutionContext:
    run_id: str
    session_id: str
    agent_id: str


@dataclass
class ToolRegistry:
    repo_tools: LocalRepoTools
    sandbox: SandboxService | None = None
    specs: dict[str, ToolSpec] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config: PlatformConfig, repo_tools: LocalRepoTools, sandbox: SandboxService | None = None) -> "ToolRegistry":
        registry = cls(repo_tools=repo_tools, sandbox=sandbox)
        for spec in builtin_tool_specs():
            registry.register(spec)
        for item in config.tools:
            registry.register(_config_to_spec(item))
        return registry

    def register(self, spec: ToolSpec) -> None:
        self.specs[spec.id] = spec

    def get(self, tool_id: str | None) -> ToolSpec | None:
        if not tool_id:
            return None
        return self.specs.get(tool_id)

    def list_specs(self) -> list[ToolSpec]:
        return sorted(self.specs.values(), key=lambda item: item.id)

    def schemas_for_tools(self, tool_ids: list[str]) -> list[dict[str, Any]]:
        return [spec.openai_tool() for tool_id in tool_ids if (spec := self.get(tool_id))]

    def execute(self, spec: ToolSpec, ctx: ToolExecutionContext, args: dict[str, Any]) -> dict[str, Any]:
        executor = spec.executor
        if executor == "builtin":
            executor = spec.id

        if executor == "repo_search":
            return self.repo_tools.repo_search(str(args.get("query", "")), int(args.get("max_results", 20)))
        if executor == "repo_read":
            return self.repo_tools.repo_read(str(args.get("path", "README.md")), int(args.get("max_chars", 4000)))
        if executor == "repo_list":
            return self.repo_tools.repo_list(str(args.get("path", ".")))
        if executor == "file_write":
            return self.repo_tools.file_write(ctx.session_id, str(args.get("path", "artifact.md")), str(args.get("content", "")))
        if executor == "file_read":
            return self.repo_tools.file_read(ctx.session_id, str(args.get("path", "artifact.md")), int(args.get("max_chars", 4000)))
        if executor == "local_command":
            if self.sandbox is None:
                return {"status": "denied", "error": "sandbox is not configured"}
            command = args.get("command", ["python", "--version"])
            if isinstance(command, str):
                command = command.split()
            return self.sandbox.execute(ctx.run_id, ctx.session_id, ctx.agent_id, list(command))
        if executor == "weather_lookup":
            return self._weather_lookup(args)
        if executor == "http_get":
            return self._http_get(spec, args)
        return {"status": "failed", "error": f"unknown executor {executor}"}

    def _weather_lookup(self, args: dict[str, Any]) -> dict[str, Any]:
        location = str(args.get("location") or args.get("city") or "Beijing")
        url = f"https://wttr.in/{location}"
        params = {"format": "j1"}
        try:
            response = httpx.get(url, params=params, timeout=12)
            response.raise_for_status()
            data = response.json()
            current = (data.get("current_condition") or [{}])[0]
            weather = {
                "location": location,
                "temperature_c": current.get("temp_C"),
                "feels_like_c": current.get("FeelsLikeC"),
                "humidity": current.get("humidity"),
                "wind_kmph": current.get("windspeedKmph"),
                "description": ((current.get("weatherDesc") or [{}])[0]).get("value"),
            }
            return {"status": "completed", "weather": weather, "source": "wttr.in"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "source": "wttr.in"}

    def _http_get(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url") or spec.config.get("url") or "")
        if not url:
            return {"status": "failed", "error": "missing url"}
        host = urlparse(url).hostname or ""
        if spec.allowed_domains and host not in spec.allowed_domains:
            return {"status": "denied", "error": f"domain not allowed: {host}"}
        try:
            response = httpx.get(url, timeout=float(spec.config.get("timeout", 15)))
            return {
                "status": "completed",
                "url": url,
                "status_code": response.status_code,
                "content": response.text[: int(spec.config.get("max_chars", 4000))],
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc), "url": url}


def builtin_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            id="repo_search",
            name="仓库搜索",
            description="在当前项目仓库中搜索文本，适合收集代码证据。参数 query 是搜索关键词，max_results 是最多返回条数。",
            category="read",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "description": "最多返回条数", "default": 20},
                },
                "required": ["query"],
            },
            is_concurrency_safe=True,
        ),
        ToolSpec(
            id="repo_read",
            name="仓库文件读取",
            description="读取当前项目仓库内的文件。只能读取仓库根目录内路径。",
            category="read",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "仓库内相对路径"},
                    "max_chars": {"type": "integer", "description": "最多读取字符数", "default": 4000},
                },
                "required": ["path"],
            },
            is_concurrency_safe=True,
        ),
        ToolSpec(
            id="repo_list",
            name="仓库目录列表",
            description="列出当前项目仓库内目录。只能列出仓库根目录内路径。",
            category="read",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "仓库内相对目录", "default": "."}},
            },
            is_concurrency_safe=True,
        ),
        ToolSpec(
            id="file_read",
            name="Session 工作区文件读取",
            description="读取当前 Session 工作区内的文件，用于读取其他 Agent 产生的 artifact。",
            category="read",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Session 工作区内相对路径"},
                    "max_chars": {"type": "integer", "description": "最多读取字符数", "default": 4000},
                },
                "required": ["path"],
            },
            is_concurrency_safe=True,
        ),
        ToolSpec(
            id="file_write",
            name="Session 工作区文件写入",
            description="把内容写入当前 Session 工作区。path 必须是相对路径，例如 story.md 或 reports/review.md，不能写绝对路径。",
            category="write",
            risk_level="medium",
            sandbox="session_workspace",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Session 工作区内相对路径，不能是绝对路径"},
                    "content": {"type": "string", "description": "要写入的完整内容"},
                },
                "required": ["path", "content"],
            },
        ),
        ToolSpec(
            id="local_command",
            name="本地只读命令",
            description="在只读沙箱中执行允许列表内的命令。适合运行 python --version、rg 等只读检查。",
            category="command",
            risk_level="medium",
            sandbox="readonly",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "命令数组，例如 ['python', '--version']",
                    }
                },
                "required": ["command"],
            },
        ),
        ToolSpec(
            id="weather_lookup",
            name="天气查询",
            description="查询指定城市的当前天气，返回温度、湿度、风速和天气描述。适合天气写作、旅行建议等任务。",
            category="network",
            executor="weather_lookup",
            risk_level="low",
            allowed_domains=["wttr.in"],
            input_schema={
                "type": "object",
                "properties": {"location": {"type": "string", "description": "城市或地区，例如 Beijing、Shanghai"}},
                "required": ["location"],
            },
            is_concurrency_safe=True,
        ),
    ]


def _config_to_spec(item: ToolConfig) -> ToolSpec:
    data = item.model_dump(mode="json")
    if not data.get("name"):
        data["name"] = item.id
    if not data.get("description"):
        data["description"] = f"Configured tool {item.id}"
    return ToolSpec.model_validate(data)


def is_workspace_relative_path(path: str) -> bool:
    if not path:
        return False
    candidate = Path(path)
    return not candidate.is_absolute() and ".." not in candidate.parts
