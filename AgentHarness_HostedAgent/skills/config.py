"""Model and runtime configuration for the Docker Sandbox AgentHarness.

Two GitHub Copilot models are exercised side-by-side:

  * GPT-6 Astra
  * GPT-5.6 Sol
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    label: str
    model_id: str


MODELS: list[ModelSpec] = [
    ModelSpec(
        label="GPT-6 Astra",
        model_id=os.getenv("MODEL_ASTRA", "gpt-6-astra"),
    ),
    ModelSpec(
        label="GPT-5.6 Sol",
        model_id=os.getenv("MODEL_SOL", "gpt-5.6-sol"),
    ),
]

REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "180"))

# Where the SessionStore writes durable session logs.
SESSION_DIR = os.getenv("SESSION_DIR", "/home/agent/state/sessions")

# GPT-6 Astra drives the harness; GPT-5.6 Sol is the comparison model.
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", MODELS[0].model_id)


def get_model(label_or_model_id: str) -> ModelSpec:
    """Look up a ModelSpec by either its label or Copilot model ID."""
    needle = label_or_model_id.strip()
    for m in MODELS:
        if needle.lower() in (m.label.lower(), m.model_id.lower()):
            return m
    raise ValueError(
        f"Unknown model '{label_or_model_id}'. Known: "
        + ", ".join(f"{m.label}({m.model_id})" for m in MODELS)
    )
