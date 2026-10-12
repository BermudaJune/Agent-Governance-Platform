from __future__ import annotations


class KeywordVectorStore:
    def __init__(self):
        self.items: list[tuple[str, str]] = []

    def add(self, item_id: str, text: str) -> None:
        self.items.append((item_id, text))

    def search(self, query: str) -> list[str]:
        return [item_id for item_id, text in self.items if query.lower() in text.lower()]
