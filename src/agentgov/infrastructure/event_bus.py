from __future__ import annotations

from collections import defaultdict
from typing import Callable


class InMemoryEventBus:
    def __init__(self):
        self.listeners = defaultdict(list)

    def publish(self, topic: str, event: dict) -> None:
        for listener in self.listeners[topic]:
            listener(event)

    def subscribe(self, topic: str, listener: Callable[[dict], None]) -> None:
        self.listeners[topic].append(listener)
