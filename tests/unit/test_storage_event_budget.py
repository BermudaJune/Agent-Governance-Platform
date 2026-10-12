from __future__ import annotations

from agentgov.budget.service import BudgetExceeded, BudgetService
from agentgov.event_stream.stream import EventStream
from agentgov.storage.db import init_db
from agentgov.storage.models import RunRecord, SessionRecord
from agentgov.storage.repositories import Repository


def test_event_stream_seq_and_budget(tmp_path):
    db = f"sqlite:///{tmp_path / 'test.db'}"
    init_db(db)
    repo = Repository(db)
    session = repo.create_session(SessionRecord(title="s", owner_id="u"))
    run = repo.create_run(RunRecord(session_id=session.id, agent_id="a", input_summary="i"))
    events = EventStream(repo)

    events.append(run.id, session.id, "run.started", "agent", "a")
    events.append(run.id, session.id, "policy.decision", "system", "policy")
    events.append(run.id, session.id, "run.final", "system", "run")

    assert [step["seq"] for step in repo.list_steps(run.id)] == [1, 2, 3]

    budget = BudgetService(repo, max_usd_per_run=0.01)
    budget.preflight(run.id, 0.0, "p", "m")
    budget.settle(run.id, 0.0, "p", "m", 1, 1)
    assert len(repo.query_all("budget_ledger", "WHERE run_id = ?", (run.id,))) == 3

    try:
        budget.preflight(run.id, 1.0, "p", "m")
    except BudgetExceeded:
        pass
    else:
        raise AssertionError("budget should be exceeded")
