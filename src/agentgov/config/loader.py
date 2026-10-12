from __future__ import annotations

from pathlib import Path

import yaml

from agentgov.config.schema import PlatformConfig


def load_config(path: str | Path) -> PlatformConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return PlatformConfig.model_validate(raw)
