from __future__ import annotations

from pathlib import Path


class LocalObjectStore:
    def __init__(self, root: str = "./data/objects"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_text(self, key: str, content: str) -> str:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path)

    def read_text(self, key: str) -> str:
        return (self.root / key).read_text(encoding="utf-8")
