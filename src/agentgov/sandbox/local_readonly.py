from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from agentgov.sandbox.base import SandboxResult


class LocalReadOnlySandboxRuntime:
    def __init__(self, root: str = ".", allowed_commands: list[str] | None = None, timeout_seconds: int = 20):
        self.root = Path(root).resolve()
        self.allowed_commands = set(allowed_commands or ["rg", "python"])
        self.timeout_seconds = timeout_seconds

    def execute(self, command: list[str], cwd: str | None = None) -> SandboxResult:
        start = time.perf_counter()
        if not command:
            return SandboxResult("failed", "", "empty command")
        if command[0] not in self.allowed_commands:
            return SandboxResult("denied", "", f"command not allowed: {command[0]}")
        workdir = (self.root / (cwd or ".")).resolve()
        if workdir != self.root and self.root not in workdir.parents:
            return SandboxResult("denied", "", "working directory escapes sandbox root")
        try:
            proc = subprocess.run(
                command,
                cwd=str(workdir),
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                env={key: os.environ[key] for key in ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP") if key in os.environ},
            )
            output = (proc.stdout + proc.stderr)[:4000]
            status = "completed" if proc.returncode == 0 else "failed"
            return SandboxResult(status, output, None if proc.returncode == 0 else f"exit code {proc.returncode}", int((time.perf_counter() - start) * 1000))
        except subprocess.TimeoutExpired:
            return SandboxResult("timeout", "", "command timed out", int((time.perf_counter() - start) * 1000))
        except OSError as exc:
            return SandboxResult("failed", "", str(exc), int((time.perf_counter() - start) * 1000))
