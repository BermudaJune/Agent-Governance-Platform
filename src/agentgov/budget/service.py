from __future__ import annotations

from agentgov.budget.ledger import BudgetLedger
from agentgov.storage.repositories import Repository


class BudgetExceeded(Exception):
    pass


class BudgetService:
    def __init__(self, repo: Repository, max_usd_per_run: float = 1.0):
        self.repo = repo
        self.ledger = BudgetLedger(repo)
        self.max_usd_per_run = max_usd_per_run

    def preflight(self, run_id: str, estimated_cost_usd: float, provider: str, model: str) -> None:
        self.ledger.write(run_id, "run", run_id, "estimate", estimated_cost_usd, "model call estimate", provider=provider, model=model)
        if estimated_cost_usd > self.max_usd_per_run:
            self.ledger.write(run_id, "run", run_id, "deny", estimated_cost_usd, "budget exceeded", provider=provider, model=model)
            raise BudgetExceeded("budget exceeded before provider call")
        self.ledger.write(run_id, "run", run_id, "reserve", estimated_cost_usd, "reserved model budget", provider=provider, model=model)

    def settle(self, run_id: str, actual_cost_usd: float, provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
        self.ledger.write(
            run_id,
            "run",
            run_id,
            "settle",
            actual_cost_usd,
            "settled actual model cost",
            provider=provider,
            model=model,
            actual_input_tokens=input_tokens,
            actual_output_tokens=output_tokens,
        )

    def release(self, run_id: str, amount_usd: float, provider: str, model: str, reason: str) -> None:
        self.ledger.write(run_id, "run", run_id, "release", amount_usd, reason, provider=provider, model=model)
