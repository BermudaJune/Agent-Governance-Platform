from __future__ import annotations

import json
import time
from collections.abc import Iterator

from agentgov.storage.repositories import Repository


def format_sse(event: dict) -> str:
    return f"id: {event['id']}\nevent: {event['event_type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def session_event_stream(repo: Repository, session_id: str, after_id: str | None = None, poll_seconds: float = 1.0) -> Iterator[str]:
    seen = {after_id} if after_id else set()
    while True:
        events = repo.query_all("run_steps", "WHERE session_id = ? ORDER BY created_at", (session_id,))
        emitted = False
        for event in events:
            if event["id"] in seen:
                continue
            seen.add(event["id"])
            emitted = True
            yield format_sse(event)
        if not emitted:
            yield ": heartbeat\n\n"
        time.sleep(poll_seconds)
