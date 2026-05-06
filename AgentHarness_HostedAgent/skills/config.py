"""Model + runtime config for the AgentHarness hosted-agent project.

Two Microsoft Foundry deployments are exercised side-by-side:

  * DeepSeek-V4-Flash  — the cost/latency optimized challenger
  * gpt-5.5            — the broad-capability incumbent

Both are reached via `agent_framework.foundry.FoundryChatClient` and
`DefaultAzureCredential`. Override the deployment names with env vars when
your Foundry project uses different names.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    label: str          # Console label
    deployment: str     # Foundry deployment name (model field for FoundryChatClient)


MODELS: list[ModelSpec] = [
    ModelSpec(
        label="DeepSeek-V4-Flash",
        # Foundry deployment name; override with MODEL_DEEPSEEK env var. The
        # default below assumes you've provisioned a DeepSeek-V3.1 deployment
        # (or whatever DeepSeek variant the manifest mapped to during
        # `azd ai agent init`). It can also be any other model — what matters
        # is that the *deployment name* exists in your Foundry project.
        deployment=os.getenv("MODEL_DEEPSEEK", "DeepSeek-V4-Flash"),
    ),
    ModelSpec(
        label="GPT-5.5",
        deployment=os.getenv("MODEL_GPT", "gpt-5.5-1"),
    ),
]

# Microsoft Foundry project endpoint; required.
PROJECT_ENDPOINT: str | None = (
    os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    or os.getenv("PROJECT_ENDPOINT")
    or os.getenv("AZURE_AI_PROJECT_ENDPOINT")
)

# Per-call timeout (seconds) handed to FoundryChatClient.
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", os.getenv("FOUNDRY_TIMEOUT", "180")))

# Where the SessionStore writes durable session logs.
SESSION_DIR = os.getenv("SESSION_DIR", "/tmp/sessions")

# Default orchestrator model — the "brain" that drives the harness tools.
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", MODELS[1].deployment)


def get_model(label_or_deployment: str) -> ModelSpec:
    """Look up a ModelSpec by either its label or its deployment string."""
    needle = label_or_deployment.strip()
    for m in MODELS:
        if needle.lower() in (m.label.lower(), m.deployment.lower()):
            return m
    raise ValueError(
        f"Unknown model '{label_or_deployment}'. Known: "
        + ", ".join(f"{m.label}({m.deployment})" for m in MODELS)
    )
