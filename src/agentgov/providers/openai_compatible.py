from __future__ import annotations

import json
import os
from typing import Any

import httpx

from agentgov.providers.scripted_model import ModelResponse


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key_env: str, model: str, timeout: float = 90, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str, agent_id: str, tools: list[dict[str, Any]] | None = None, system_prompt: str = "") -> ModelResponse:
        api_key = self.api_key or os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"missing API key; set provider api_key or env: {self.api_key_env}")
        system_parts = [
            f"You are {agent_id} in an agent governance platform.",
            "When a listed tool is useful, call it with structured arguments instead of only describing the action.",
            "Use file_write with a relative path inside the current Session workspace, never an absolute path.",
        ]
        if system_prompt:
            system_parts.append(system_prompt)
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "\n".join(system_parts)},
                {"role": "user", "content": prompt},
            ],
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        message = data["choices"][0]["message"]
        content = message.get("content") or ""
        usage = data.get("usage", {})
        tool_intent = _parse_tool_intent(message)
        return ModelResponse(
            content=content,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            tool_intent=tool_intent,
        )


def _parse_tool_intent(message: dict[str, Any]) -> dict[str, Any] | None:
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        name = function.get("name")
        if not name:
            continue
        raw_args = function.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
        except (TypeError, ValueError):
            args = {"raw_arguments": raw_args}
        calls.append({"tool": name, "tool_call_id": call.get("id"), **args})
    if not calls:
        return None
    return {"calls": calls}
