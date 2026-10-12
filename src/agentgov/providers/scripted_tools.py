from __future__ import annotations


class ScriptedTools:
    def call(self, name: str, args: dict) -> dict:
        return {"tool": name, "args": args, "status": "completed", "scripted": True}
