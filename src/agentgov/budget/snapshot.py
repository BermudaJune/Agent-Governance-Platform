from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BudgetSnapshot:
    scope: str
    max_budget_usd: float | None
    current_spend_usd: float
    reserved_spend_usd: float
