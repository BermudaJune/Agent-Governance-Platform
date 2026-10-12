from __future__ import annotations

import pytest

from agentgov.config.loader import load_config


def test_local_openai_config_valid():
    cfg = load_config("config/examples/local.openai.yaml")
    assert cfg.providers[0].protocol.value == "openai"
    assert len(cfg.agents) >= 7
    assert {agent.id for agent in cfg.agents} >= {"story_writer", "story_reviewer"}


def test_plain_api_key_is_supported_for_local_config(tmp_path):
    path = tmp_path / "local-key.yaml"
    path.write_text(
        """
providers:
  - name: local
    protocol: openai
    base_url: https://example.test/v1
    api_key: secret
    model: test-model
agents:
  - id: agent
    name: Agent
    provider: local
    model: test-model
""",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.providers[0].api_key == "secret"
