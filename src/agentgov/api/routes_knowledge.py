from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agentgov.knowledge.models import KnowledgeSourceInput
from agentgov.storage.models import now_iso
from agentgov.storage.repositories import Repository


class KnowledgeSourceRequest(KnowledgeSourceInput):
    pass


class KnowledgeSearchRequest(BaseModel):
    query: str = ""
    run_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


def router(repo: Repository) -> APIRouter:
    r = APIRouter(tags=["knowledge"])

    @r.get("/sessions/{session_id}/knowledge")
    def list_knowledge(session_id: str):
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        session = repo.get_session(session_id) or {}
        return {
            "session_id": session_id,
            "policy": (session.get("metadata") or {}).get("knowledge_policy", {}),
            "sources": repo.list_session_knowledge(session_id),
            "grants": repo.list_knowledge_grants(session_id),
        }

    @r.post("/sessions/{session_id}/knowledge")
    def add_knowledge(session_id: str, req: KnowledgeSourceRequest):
        if repo.get_session(session_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown session: {session_id}")
        if not req.content.strip() and not (req.locator or "").strip():
            raise HTTPException(status_code=400, detail="knowledge source requires content or locator")
        source_id = repo.add_session_knowledge(session_id, req.model_dump())
        return {"source": next(item for item in repo.list_session_knowledge(session_id) if item["id"] == source_id)}

    @r.get("/runs/{run_id}/knowledge-context")
    def knowledge_context(run_id: str):
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
        grants = repo.list_knowledge_grants_for_run(run_id)
        sources = {item["id"]: item for item in repo.list_session_knowledge(run["session_id"])}
        return {
            "run_id": run_id,
            "agent_id": run["agent_id"],
            "grants": grants,
            "sources": [sources[source_id] for grant in grants for source_id in grant.get("source_ids", []) if source_id in sources],
            "events": repo.query_all("knowledge_access_events", "WHERE run_id = ? ORDER BY created_at", (run_id,)),
        }

    @r.post("/runs/{run_id}/knowledge-search")
    def search_knowledge(run_id: str, req: KnowledgeSearchRequest):
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
        query = req.query.strip().lower()
        session = repo.get_session(run["session_id"]) or {}
        policy = (session.get("metadata") or {}).get("knowledge_policy") or {}
        if policy.get("allow_agent_search") is False:
            repo.insert_generic(
                "knowledge_access_events",
                {
                    "session_id": run["session_id"],
                    "run_id": run_id,
                    "agent_id": run["agent_id"],
                    "source_id": None,
                    "action": "knowledge_search",
                    "query": req.query,
                    "result_refs": [],
                    "decision": "deny",
                    "reason": "Session policy disables Agent search",
                    "created_at": now_iso(),
                },
            )
            return {"run_id": run_id, "query": req.query, "results": [], "result_refs": [], "decision": "deny"}
        grants = repo.list_knowledge_grants_for_run(run_id)
        allowed_ids = {source_id for grant in grants if grant.get("status") == "planned" for source_id in grant.get("source_ids", [])}
        sources = [item for item in repo.list_session_knowledge(run["session_id"]) if item["id"] in allowed_ids and (not query or query in f"{item['name']} {item.get('content', '')}".lower())]
        refs = [item["id"] for item in sources[: req.limit]]
        for source_id in refs:
            repo.insert_generic(
                "knowledge_access_events",
                {
                    "session_id": run["session_id"],
                    "run_id": run_id,
                    "agent_id": run["agent_id"],
                    "source_id": source_id,
                    "action": "knowledge_search",
                    "query": req.query,
                    "result_refs": refs,
                    "decision": "allow",
                    "reason": "source is included in the Leader grant",
                    "created_at": now_iso(),
                },
            )
        return {"run_id": run_id, "query": req.query, "results": sources[: req.limit], "result_refs": refs}

    return r
