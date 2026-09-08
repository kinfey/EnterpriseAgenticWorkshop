"""In-process hand registry.

The process itself is isolated by Docker Sandboxes. This registry only
dispatches named harness operations through one signature:
    execute(name, input) -> str
"""
from __future__ import annotations

from typing import Any, Callable

from .vault import CredentialVault


class HandError(Exception):
    """Raised when a hand call fails. The brain treats it as a tool error."""


ToolFn = Callable[[dict[str, Any], CredentialVault], str]


class HandPool:
    def __init__(self, vault: CredentialVault, max_output_chars: int = 12000) -> None:
        self._vault = vault
        self._max_output = max_output_chars
        self._tools: dict[str, ToolFn] = {}
        self._descriptions: dict[str, str] = {}

    def register(self, name: str, fn: ToolFn, description: str = "") -> None:
        self._tools[name] = fn
        self._descriptions[name] = description

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {"name": n, "description": self._descriptions.get(n, "")}
            for n in sorted(self._tools.keys())
        ]

    def execute(self, name: str, input: dict[str, Any]) -> str:
        if name not in self._tools:
            return f"ERROR: unknown tool '{name}'. Available: {[t['name'] for t in self.list_tools()]}"
        try:
            out = self._tools[name](input or {}, self._vault)
            out = self._vault.redact(out)
            if len(out) > self._max_output:
                out = out[: self._max_output] + f"\n...[truncated {len(out) - self._max_output} chars]"
            return out
        except HandError as e:
            return f"ERROR: hand '{name}' failed: {e}"
        except Exception as e:  # noqa: BLE001
            return f"ERROR: hand '{name}' failed: {type(e).__name__}: {e}"
