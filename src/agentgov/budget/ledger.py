from __future__ import annotations

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class BudgetLedger:
    def __init__(self, repo: Repository):
        self.repo = repo

    def write(self, run_id: str, scope_type: str, scope_id: str, entry_type: str, amount_usd: float, reason: str, **extra) -> str:
        return self.repo.insert_generic(
            "budget_ledger",
            {
                "run_id": run_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "entry_type": entry_type,
                "amount_usd": amount_usd,
                "reason": reason,
                "created_at": now_iso(),
                **extra,
            },
        )
