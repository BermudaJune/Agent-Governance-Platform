from __future__ import annotations

from fastapi import APIRouter

from agentgov.config.loader import load_config


def router(config_path: str) -> APIRouter:
    r = APIRouter(prefix="/agents", tags=["agents"])

    @r.get("")
    def list_agents():
        cfg = load_config(config_path)
        return [agent.model_dump() for agent in cfg.agents]

    return r
