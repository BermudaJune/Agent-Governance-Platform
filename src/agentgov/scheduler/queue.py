from __future__ import annotations

from agentgov.storage.models import now_iso, new_id
from agentgov.storage.repositories import Repository
from agentgov.storage.db import connect


class RunQueue:
    def __init__(self, repo: Repository):
        self.repo = repo

    def enqueue(self, run_id: str, session_id: str | None = None, priority: int = 100) -> str:
        run = self.repo.get_run(run_id)
        session_id = session_id or (run["session_id"] if run else None)
        return self.repo.insert_generic(
            "run_queue",
            {
                "run_id": run_id,
                "session_id": session_id,
                "status": "queued",
                "priority": priority,
                "lease_owner": None,
                "attempts": 0,
                "last_error": None,
                "available_at": now_iso(),
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )

    def lease_next(self, worker_id: str) -> dict | None:
        with connect(self.repo.database) as conn:
            row = conn.execute(
                """
                SELECT * FROM run_queue
                WHERE status = 'queued' AND available_at <= ?
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
                """,
                (now_iso(),),
            ).fetchone()
            if row is None:
                return None
            item = dict(row)
            conn.execute(
                """
                UPDATE run_queue
                SET status = 'leased', lease_owner = ?, attempts = attempts + 1, updated_at = ?
                WHERE id = ?
                """,
                (worker_id, now_iso(), item["id"]),
            )
            conn.execute(
                """
                INSERT INTO run_leases (id, run_id, worker_id, lease_until, heartbeat_at, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (new_id(), item["run_id"], worker_id, now_iso(), now_iso(), "active", now_iso()),
            )
            conn.commit()
            item["status"] = "leased"
            item["lease_owner"] = worker_id
            return item

    def complete(self, item_id: str) -> None:
        self.repo.update_generic("run_queue", item_id, {"status": "completed", "updated_at": now_iso()})

    def fail(self, item_id: str, error: str, retryable: bool = False) -> None:
        status = "queued" if retryable else "failed"
        self.repo.update_generic(
            "run_queue",
            item_id,
            {"status": status, "last_error": error, "lease_owner": None, "updated_at": now_iso()},
        )

    def cancel_run(self, run_id: str) -> int:
        with connect(self.repo.database) as conn:
            cur = conn.execute(
                "UPDATE run_queue SET status = 'cancelled', updated_at = ? WHERE run_id = ? AND status IN ('queued', 'leased')",
                (now_iso(), run_id),
            )
            conn.commit()
            return cur.rowcount

    def cancel_session(self, session_id: str) -> int:
        with connect(self.repo.database) as conn:
            cur = conn.execute(
                """
                UPDATE run_queue
                SET status = 'cancelled', updated_at = ?
                WHERE session_id = ? AND status IN ('queued', 'leased')
                """,
                (now_iso(), session_id),
            )
            conn.commit()
            return cur.rowcount
