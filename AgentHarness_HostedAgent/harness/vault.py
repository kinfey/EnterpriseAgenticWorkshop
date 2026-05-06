"""Credential vault.

Tokens are referenced by logical name; the vault injects them only at the
sandbox boundary, so neither the model nor the running tool ever sees the
raw secret.
"""
from __future__ import annotations

import os
from typing import Any


class CredentialVault:
    def __init__(self, secrets: dict[str, str] | None = None) -> None:
        self._secrets: dict[str, str] = dict(secrets or {})

    def register_env(self, logical_name: str, env_var: str) -> None:
        value = os.getenv(env_var)
        if value is not None:
            self._secrets[logical_name] = value

    def resolve(self, logical_name: str) -> str | None:
        return self._secrets.get(logical_name)

    def has(self, logical_name: str) -> bool:
        return logical_name in self._secrets

    def build_auth_headers(self, logical_name: str) -> dict[str, str]:
        token = self.resolve(logical_name)
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def redact(self, value: Any) -> Any:
        s = str(value)
        for secret in self._secrets.values():
            if secret and secret in s:
                s = s.replace(secret, "***REDACTED***")
        return s
