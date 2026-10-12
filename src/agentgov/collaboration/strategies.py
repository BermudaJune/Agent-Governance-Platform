from __future__ import annotations

from typing import Protocol


class CollaborationStrategy(Protocol):
    def run(self, parent_run_id: str) -> dict:
        ...
