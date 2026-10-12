from __future__ import annotations

from agentgov.gateway.model import ModelGateway
from agentgov.gateway.tool import ToolGateway


class AgentLoop:
    def __init__(self, model_gateway: ModelGateway, tool_gateway: ToolGateway, max_turns: int = 4):
        self.model_gateway = model_gateway
        self.tool_gateway = tool_gateway
        self.max_turns = max_turns

    def run_once(self, run_id: str, session_id: str, agent_id: str, prompt: str) -> dict:
        tools = self.tool_gateway.schemas_for_agent(agent_id)
        current_prompt = prompt
        final_response = ""
        tool_result = None
        tool_results = []
        for turn in range(1, self.max_turns + 1):
            response = self.model_gateway.complete(run_id, session_id, agent_id, current_prompt, tools=tools)
            final_response = response.content or final_response
            if not response.tool_intent:
                break
            intent = response.tool_intent
            calls = intent.get("calls") if isinstance(intent.get("calls"), list) else [intent]
            observations = []
            for call in calls:
                tool_name = call.get("tool")
                args = {k: v for k, v in call.items() if k != "tool"}
                tool_result = self.tool_gateway.call(run_id, session_id, agent_id, tool_name, args)
                tool_results.append(tool_result)
                observations.append({"tool": tool_name, "result": tool_result})
            if any(item.get("status") == "awaiting_approval" for item in tool_results):
                return {
                    "response": final_response,
                    "tool_result": tool_result,
                    "tool_results": tool_results,
                    "requires_approval": True,
                }
            if final_response.strip():
                break
            current_prompt = (
                f"{prompt}\n\n"
                "Tool observations from the governed platform are below. Use them to continue or finish the task.\n"
                f"{observations}"
            )
        return {"response": final_response, "tool_result": tool_result, "tool_results": tool_results}
