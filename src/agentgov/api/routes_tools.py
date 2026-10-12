from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentgov.config.loader import load_config
from agentgov.config.schema import PlatformConfig, ToolConfig
from agentgov.gateway.tool_registry import ToolRegistry, _config_to_spec


class RegisterToolRequest(BaseModel):
    tool: ToolConfig


def router(config_path: str, registry: ToolRegistry) -> APIRouter:
    r = APIRouter(prefix="/tools", tags=["tools"])
    path = Path(config_path)

    @r.get("")
    def list_tools():
        cfg = load_config(path)
        configured_ids = {tool.id for tool in cfg.tools}
        return [
            {
                **spec.model_dump(mode="json"),
                "source": "config" if spec.id in configured_ids else "builtin",
                "openai_schema": spec.openai_tool(),
            }
            for spec in registry.list_specs()
        ]

    @r.post("/register")
    def register_tool(req: RegisterToolRequest):
        cfg = load_config(path)
        _validate_executor(req.tool)
        tools = [tool for tool in cfg.tools if tool.id != req.tool.id]
        tools.append(req.tool)
        data = cfg.model_dump(mode="json")
        data["tools"] = [tool.model_dump(mode="json") for tool in tools]
        next_cfg = PlatformConfig.model_validate(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(next_cfg.model_dump(mode="json"), allow_unicode=True, sort_keys=False), encoding="utf-8")
        registry.register(_config_to_spec(req.tool))
        return {"registered": True, "tool": req.tool.model_dump(mode="json"), "restart_required": False}

    return r


def _validate_executor(tool: ToolConfig) -> None:
    allowed = {"builtin", "repo_search", "repo_read", "repo_list", "file_read", "file_write", "local_command", "weather_lookup", "http_get"}
    if tool.executor not in allowed:
        raise HTTPException(status_code=400, detail=f"unsupported executor: {tool.executor}")
    if tool.executor == "http_get" and not tool.allowed_domains:
        raise HTTPException(status_code=400, detail="http_get tools must set allowed_domains")
    if not isinstance(tool.input_schema, dict) or tool.input_schema.get("type") != "object":
        raise HTTPException(status_code=400, detail="input_schema must be a JSON schema object")
