from __future__ import annotations

from agentgov.runtime.run_service import RunService
from agentgov.scheduler.queue import RunQueue
from agentgov.event_stream.stream import EventStream


class RunWorker:
    def __init__(self, service: RunService, queue: RunQueue | None = None, events: EventStream | None = None, worker_id: str = "local-worker"):
        self.service = service
        self.queue = queue
        self.events = events
        self.worker_id = worker_id

    def execute(self, run_id: str) -> dict:
        return self.service.execute(run_id)

    def tick(self) -> int:
        if self.queue is None:
            return 0
        item = self.queue.lease_next(self.worker_id)
        if item is None:
            return 0
        run = self.service.repo.get_run(item["run_id"])
        if not run:
            self.queue.fail(item["id"], "run not found", retryable=False)
            return 1
        if self.events:
            self.events.append(run["id"], run["session_id"], "queue.item.leased", "system", self.worker_id, "started", {"queue_item_id": item["id"]})
        result = self.service.execute(run["id"])
        if result.get("status") == "completed":
            self.queue.complete(item["id"])
            if self.events:
                self.events.append(run["id"], run["session_id"], "queue.item.completed", "system", self.worker_id, "completed", {"queue_item_id": item["id"]})
        elif result.get("status") in {"paused", "cancelled"}:
            self.queue.fail(item["id"], result.get("error") or result["status"], retryable=False)
            if self.events:
                self.events.append(run["id"], run["session_id"], "queue.item.cancelled", "system", self.worker_id, "cancelled", {"queue_item_id": item["id"]})
        else:
            self.queue.fail(item["id"], result.get("error") or "run failed", retryable=False)
            if self.events:
                self.events.append(run["id"], run["session_id"], "queue.item.failed", "system", self.worker_id, "failed", {"queue_item_id": item["id"], "error": result.get("error")})
        return 1
