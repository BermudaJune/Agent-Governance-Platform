from __future__ import annotations

from pathlib import Path


class LocalRepoTools:
    def __init__(self, root: str = "."):
        self.root = Path(root).resolve()

    def _safe_path(self, path: str) -> Path:
        resolved = (self.root / path).resolve()
        if not str(resolved).startswith(str(self.root)):
            raise PermissionError("path escapes repository root")
        return resolved

    def repo_list(self, path: str = ".") -> dict:
        target = self._safe_path(path)
        return {"path": str(target), "items": sorted(p.name for p in target.iterdir())[:200]}

    def repo_read(self, path: str, max_chars: int = 4000) -> dict:
        target = self._safe_path(path)
        return {"path": str(target), "content": target.read_text(encoding="utf-8", errors="ignore")[:max_chars]}

    def repo_search(self, query: str, max_results: int = 20) -> dict:
        matches = []
        for path in self.root.rglob("*"):
            if len(matches) >= max_results:
                break
            if path.is_file() and path.stat().st_size < 500_000:
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if query.lower() in text.lower():
                    matches.append({"path": str(path.relative_to(self.root)), "snippet": query})
        return {"query": query, "matches": matches}

    def _workspace_path(self, session_id: str, path: str) -> Path:
        workspace = (self.root / "data" / "workspaces" / session_id).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        target = (workspace / path).resolve()
        if not str(target).startswith(str(workspace)):
            raise PermissionError("path escapes session workspace")
        return target

    def file_write(self, session_id: str, path: str, content: str) -> dict:
        target = self._workspace_path(session_id, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {
            "status": "completed",
            "path": str(target),
            "relative_path": str(target.relative_to(self.root)),
            "bytes": len(content.encode("utf-8")),
            "preview": content[:500],
        }

    def file_read(self, session_id: str, path: str, max_chars: int = 4000) -> dict:
        target = self._workspace_path(session_id, path)
        content = target.read_text(encoding="utf-8", errors="ignore")
        return {
            "status": "completed",
            "path": str(target),
            "relative_path": str(target.relative_to(self.root)),
            "content": content[:max_chars],
            "truncated": len(content) > max_chars,
        }
