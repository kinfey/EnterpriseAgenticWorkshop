"""Sandbox pool ("hands").

Cattle-not-pets: each sandbox is provisioned lazily, retired after exactly
one call. The brain interacts with every hand through one signature:
    execute(name, input) -> str
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from .vault import CredentialVault


class SandboxError(Exception):
    """Raised when a sandbox call fails. The brain treats it as a tool error."""


@dataclass
class _Sandbox:
    kind: str
    sandbox_id: str
    created_at: float


ToolFn = Callable[[dict[str, Any], CredentialVault], str]


class SandboxPool:
    def __init__(self, vault: CredentialVault, max_output_chars: int = 12000) -> None:
        self._vault = vault
        self._max_output = max_output_chars
        self._tools: dict[str, ToolFn] = {}
        self._descriptions: dict[str, str] = {}
        self._active: dict[str, _Sandbox] = {}

    def register(self, name: str, fn: ToolFn, description: str = "") -> None:
        self._tools[name] = fn
        self._descriptions[name] = description

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": n, "description": self._descriptions.get(n, "")}
            for n in sorted(self._tools.keys())
        ]

    def provision(self, kind: str) -> str:
        sid = f"{kind}-{int(time.time() * 1000)}"
        self._active[sid] = _Sandbox(kind=kind, sandbox_id=sid, created_at=time.time())
        return sid

    def retire(self, sandbox_id: str) -> None:
        self._active.pop(sandbox_id, None)

    def execute(self, name: str, input: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"ERROR: unknown tool '{name}'. Available: {[t['name'] for t in self.list_tools()]}"
        sandbox_id = self.provision(kind=name)
        try:
            out = self._tools[name](input or {}, self._vault)
            out = self._vault.redact(out)
            if len(out) > self._max_output:
                out = out[: self._max_output] + f"\n...[truncated {len(out) - self._max_output} chars]"
            return out
        except SandboxError as e:
            return f"ERROR: sandbox '{sandbox_id}' failed: {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: sandbox '{sandbox_id}' failed: {type(e).__name__}: {e}"
        finally:
            self.retire(sandbox_id)
