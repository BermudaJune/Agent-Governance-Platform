from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class RunLease:
    def __init__(self, repo: Repository):
        self.repo = repo

    def claim(self, run_id: str, worker_id: str, seconds: int = 30) -> str:
        lease_until = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        return self.repo.insert_generic(
            "run_leases",
            {
                "run_id": run_id,
                "worker_id": worker_id,
                "lease_until": lease_until,
                "heartbeat_at": now_iso(),
                "status": "active",
                "created_at": now_iso(),
            },
        )
