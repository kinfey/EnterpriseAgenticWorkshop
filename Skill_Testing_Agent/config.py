"""Model configuration for the testing harness.

Two backends are exercised through the GitHub Copilot CLI: GPT-6 Astra and
Grok 4.6. The exact model IDs accepted by `copilot --model` change over time;
override with env vars `MODEL_GPT` / `MODEL_GROK` if needed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    label: str          # Human-readable label shown in the console
    model_id: str       # Value passed to GitHub Copilot CLI as --model


MODELS: list[ModelSpec] = [
    ModelSpec(
        label="GPT-6 Astra",
        model_id=os.getenv("MODEL_GPT", "gpt-6-astra"),
    ),
    ModelSpec(
        label="Grok 4.6",
        model_id=os.getenv("MODEL_GROK", "grok-4.6"),
    ),
]

# Per-call timeout (seconds) handed to the Copilot CLI.
REQUEST_TIMEOUT = int(os.getenv("GITHUB_COPILOT_TIMEOUT", "180"))
