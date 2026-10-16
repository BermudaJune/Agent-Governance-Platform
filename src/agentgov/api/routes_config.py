from __future__ import annotations

import os
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
        data = cfg.model_dump(mode="json")
        for provider in data.get("providers", []):
            configured = bool(provider.get("api_key"))
            if provider.get("api_key"):
                provider["api_key"] = None
            if provider.get("api_key_env"):
                configured = configured or bool(os.getenv(provider["api_key_env"]))
            provider["api_key_configured"] = configured
            models = provider.get("models") or []
            provider["effective_model"] = provider.get("model") or (models[0].get("name") if models else None)
        return {
            "path": str(path),
            "config": data,
            "note": "Provider changes require backend restart. Use api_key_env; the API never returns api_key to the browser.",
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
