"""Deterministic browser verification only. Never imported by the application."""
import json
from pathlib import Path

import uvicorn

from agentgov.app import create_app
from agentgov.providers.openai_compatible import OpenAICompatibleProvider
from agentgov.providers.scripted_model import ModelResponse


def complete(self, prompt, agent_id, **kwargs):
    if not kwargs.get("tools"):
        if "capability-route-check" in prompt and "针对能力缺口" not in prompt:
            return ModelResponse(json.dumps({
                "understanding": "Illustrations require an unavailable runtime", "reply": "Please choose how to proceed",
                "nodes": [], "capability_gaps": [
                    {"capability": "illustrations", "reason": "No configured image runtime"},
                    {"capability": "weather", "reason": "No live weather service"},
                    {"capability": "slides", "reason": "No slide renderer"},
                ]}), 25, 30)
        revised = "change-ending" in prompt
        nodes = [{"node_key": "write", "assigned_agent_id": "writer", "title": "Draft story",
                  "instruction": "Write the story" + (" with a new ending" if revised else ""),
                  "required_tools": ["file_write"], "output_contract": {"files": ["story.md"]}},
                 {"node_key": "review", "assigned_agent_id": "coordinator", "title": "Review story",
                  "instruction": "Review the story and save review.md", "depends_on": ["write"],
                  "required_tools": ["file_write"], "output_contract": {"files": ["review.md"]}}]
        if revised:
            nodes.append({"node_key": "verify", "assigned_agent_id": "coordinator", "title": "Verify delivery",
                          "instruction": "Verify both results are present", "depends_on": ["review"]})
        result = {"understanding": "A short story with conflict and a twist", "reply": "Revised the ending and added final verification" if revised else "Draft, then review for conflict and a twist",
                  "acceptance": ["A real story.md file", "A review.md file with concrete feedback"], "nodes": nodes}
        return ModelResponse(json.dumps(result), 25, 30)
    if "Verify both results" in prompt:
        return ModelResponse("Verified story.md and review.md. Ready for your acceptance.", 10, 10)
    review = "Review the story and save review.md" in prompt
    name = "review.md" if review else "story.md"
    if '"status": "completed"' in prompt:
        return ModelResponse("Saved " + name + "; available in Session artifacts.", 15, 15)
    content = "Review: clear conflict, surprising ending, requirements met." if review else "The lighthouse went dark. Lin lit a match, revealing the missing keeper beside her. He had returned to warn her: the light had been guiding ships toward the reef. Together they turned it inland."
    return ModelResponse("", 10, 10, tool_intent={"tool": "file_write", "path": name, "content": content})


if __name__ == "__main__":
    OpenAICompatibleProvider.complete = complete
    import agentgov.runtime.leader_workflow as workflow
    workflow.search_github_skill_repositories = lambda query, limit: []
    config = Path("output/browser-validation.yaml")
    config.write_text("""
providers:
  - name: browser-fixture-only
    protocol: openai
    base_url: https://example.test/v1
    model: fixture
tools:
  - id: file_write
    name: Reviewed write
    executor: file_write
    category: write
    requires_approval: true
agents:
  - id: coordinator
    name: Leader
    provider: browser-fixture-only
    model: fixture
    tools: [file_write, file_read]
  - id: writer
    name: Writer
    provider: browser-fixture-only
    model: fixture
    tools: [file_write, file_read]
""", encoding="utf-8")
    uvicorn.run(create_app(database="sqlite:///./output/browser-validation.db", config_path=str(config)), host="127.0.0.1", port=8008)
