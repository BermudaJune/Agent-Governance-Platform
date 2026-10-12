from __future__ import annotations

from agentgov.budget.service import BudgetService
from agentgov.event_stream.stream import EventStream
from agentgov.providers.scripted_model import ModelResponse
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class ModelGateway:
    def __init__(
        self,
        repo: Repository,
        events: EventStream,
        budget: BudgetService,
        provider,
        provider_name: str,
        model: str,
        input_price_per_1k: float = 0.0,
        output_price_per_1k: float = 0.0,
        system_prompts_by_agent: dict[str, str] | None = None,
    ):
        self.repo = repo
        self.events = events
        self.budget = budget
        self.provider = provider
        self.provider_name = provider_name
        self.model = model
        self.input_price_per_1k = input_price_per_1k
        self.output_price_per_1k = output_price_per_1k
        self.system_prompts_by_agent = system_prompts_by_agent or {}

    def complete(self, run_id: str, session_id: str, agent_id: str, prompt: str, tools: list[dict] | None = None) -> ModelResponse:
        estimated_cost = 0.0
        self.budget.preflight(run_id, estimated_cost, self.provider_name, self.model)
        start_step = self.events.append(
            run_id,
            session_id,
            "model.call.started",
            "agent",
            agent_id,
            "started",
            {"model": self.model, "tool_schema_count": len(tools or [])},
        )
        try:
            response = self.provider.complete(
                prompt,
                agent_id,
                tools=tools or [],
                system_prompt=self.system_prompts_by_agent.get(agent_id, ""),
            )
        except Exception as exc:
            self.budget.release(run_id, estimated_cost, self.provider_name, self.model, "provider failure")
            failed_step = self.events.append(
                run_id,
                session_id,
                "model.call.failed",
                "agent",
                agent_id,
                "failed",
                {"model": self.model, "error": str(exc), "request": prompt[:500]},
            )
            self.repo.insert_generic(
                "model_calls",
                {
                    "run_id": run_id,
                    "step_id": failed_step.id,
                    "provider": self.provider_name,
                    "model": self.model,
                    "request_summary": prompt[:500],
                    "response_summary": "",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "estimated_cost_usd": estimated_cost,
                    "actual_cost_usd": 0,
                    "status": "failed",
                    "error": str(exc),
                    "created_at": now_iso(),
                },
            )
            raise
        actual_cost = (
            response.input_tokens * self.input_price_per_1k / 1000
            + response.output_tokens * self.output_price_per_1k / 1000
        )
        self.budget.settle(run_id, actual_cost, self.provider_name, self.model, response.input_tokens, response.output_tokens)
        self.repo.add_run_usage(run_id, response.input_tokens, response.output_tokens, actual_cost)
        finish_step = self.events.append(
            run_id,
            session_id,
            "model.call.finished",
            "agent",
            agent_id,
            "completed",
            {"model": self.model, "response": response.content, "tool_intent": response.tool_intent},
        )
        self.repo.insert_generic(
            "model_calls",
            {
                "run_id": run_id,
                "step_id": finish_step.id,
                "provider": self.provider_name,
                "model": self.model,
                "request_summary": prompt[:500],
                "response_summary": response.content[:500],
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "estimated_cost_usd": estimated_cost,
                "actual_cost_usd": actual_cost,
                "status": "completed",
                "created_at": now_iso(),
            },
        )
        return response
