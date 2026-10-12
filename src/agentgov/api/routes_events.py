from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from agentgov.event_stream.sse import session_event_stream
from agentgov.storage.repositories import Repository


def router(repo: Repository) -> APIRouter:
    r = APIRouter(prefix="/events", tags=["events"])

    @r.get("/sessions/{session_id}")
    def session_events(session_id: str, after_id: str | None = None):
        return StreamingResponse(session_event_stream(repo, session_id, after_id), media_type="text/event-stream")

    return r
