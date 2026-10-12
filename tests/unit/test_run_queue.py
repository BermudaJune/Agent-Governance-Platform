from __future__ import annotations

from agentgov.scheduler.queue import RunQueue
from agentgov.storage.db import init_db
from agentgov.storage.models import RunRecord, SessionRecord
from agentgov.storage.repositories import Repository


def test_run_queue_lease_complete_and_cancel(tmp_path):
    db = f"sqlite:///{tmp_path / 'queue.db'}"
    init_db(db)
    repo = Repository(db)
    session = repo.create_session(SessionRecord(title="queue", owner_id="test"))
    run = repo.create_run(RunRecord(session_id=session.id, agent_id="agent", input_summary="work"))
    queue = RunQueue(repo)

    item_id = queue.enqueue(run.id, session.id)
    item = queue.lease_next("worker-1")

    assert item is not None
    assert item["id"] == item_id
    assert item["status"] == "leased"

    queue.complete(item_id)
    rows = repo.query_all("run_queue", "WHERE id = ?", (item_id,))
    assert rows[0]["status"] == "completed"

    second = queue.enqueue(run.id, session.id)
    assert queue.cancel_session(session.id) == 1
    rows = repo.query_all("run_queue", "WHERE id = ?", (second,))
    assert rows[0]["status"] == "cancelled"
