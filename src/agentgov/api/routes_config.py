from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter
from pydantic import BaseModel

from agentgov.config.loader import load_config
from agentgov.config.schema import PlatformConfig


class ConfigSaveRequest(BaseModel):
    config: dict[str, Any]


def router(config_path: str) -> APIRouter:
    r = APIRouter(prefix="/config", tags=["config"])
    path = Path(config_path)

    @r.get("")
    def get_config():
        cfg = load_config(path)
        return {
            "path": str(path),
            "config": cfg.model_dump(mode="json"),
            "note": "Provider changes require backend restart. Local configs may use api_key or api_key_env.",
        }

    @r.post("/validate")
    def validate_config(req: ConfigSaveRequest):
        cfg = PlatformConfig.model_validate(req.config)
        return {
            "valid": True,
            "providers": len(cfg.providers),
            "agents": len(cfg.agents),
            "teams": len(cfg.teams),
        }

    @r.put("")
    def save_config(req: ConfigSaveRequest):
        cfg = PlatformConfig.model_validate(req.config)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(cfg.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        return {
            "saved": True,
            "path": str(path),
            "restart_required": True,
            "reason": "Agent list updates immediately through /agents; provider/runtime wiring is rebuilt on backend restart.",
        }

    return r
