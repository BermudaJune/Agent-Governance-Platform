from __future__ import annotations

from agentgov.collaboration.team_bus import TeamBus
from agentgov.storage.models import RunRecord, now_iso
from agentgov.storage.repositories import Repository


class LeaderWorkerStrategy:
    def __init__(self, repo: Repository, bus: TeamBus):
        self.repo = repo
        self.bus = bus

    def delegate_all(self, session_id: str, parent_run_id: str, leader: str, workers: list[str]) -> list[str]:
        child_ids = []
        for worker in workers:
            self.bus.publish(parent_run_id, session_id, leader, worker, "task.assigned", {"instruction": f"work assigned to {worker}"}, parent_run_id)
            child = self.repo.create_run(
                RunRecord(
                    session_id=session_id,
                    parent_run_id=parent_run_id,
                    agent_id=worker,
                    input_summary=f"delegated task for {worker}",
                    status="completed",
                    started_at=now_iso(),
                    completed_at=now_iso(),
                    output_summary=f"{worker} completed",
                )
            )
            child_ids.append(child.id)
            self.bus.publish(parent_run_id, session_id, worker, leader, "task.result", {"child_run_id": child.id}, parent_run_id)
        return child_ids
