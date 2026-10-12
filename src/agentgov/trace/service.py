from __future__ import annotations

from agentgov.storage.repositories import Repository
from agentgov.trace.evidence import EvidenceService
from agentgov.trace.reasoning import ReasoningTraceService
from agentgov.trace.spans import SpanService


class TraceService:
    def __init__(self, repo: Repository):
        self.spans = SpanService(repo)
        self.evidence = EvidenceService(repo)
        self.reasoning = ReasoningTraceService(repo)
