"""GitHub Copilot-backed factory for one-shot agent runs.

The adversarial test agent, the business agent and the judge are all just
`GitHubCopilotAgent(...)` instances. They differ only in the system prompt
and selected GitHub Copilot model.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from agent_framework.github import GitHubCopilotAgent
from copilot import CopilotClient
from copilot.session import PermissionHandler

from .config import REQUEST_TIMEOUT


def make_copilot_client() -> CopilotClient:
    """Create a client that prefers the OAuth login stored in the sandbox."""
    env = dict(os.environ)
    if env.get("COPILOT_USE_LOGGED_IN_USER", "1").lower() in {"1", "true", "yes"}:
        for name in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
            env.pop(name, None)
    return CopilotClient(env=env, use_logged_in_user=True)


@asynccontextmanager
async def make_agent(
    model_id: str,
    instructions: str,
    name: str,
) -> AsyncIterator[GitHubCopilotAgent]:
    """Yield a ready-to-use agent backed by GitHub Copilot."""
    agent = GitHubCopilotAgent(
        client=make_copilot_client(),
        instructions=instructions,
        name=name,
        default_options={
            "model": model_id,
            "timeout": REQUEST_TIMEOUT,
            "on_permission_request": PermissionHandler.approve_all,
        },
    )
    async with agent:
        yield agent


async def run_once(model_id: str, instructions: str, name: str, prompt: str) -> str:
    import asyncio

    async with make_agent(model_id, instructions, name) as agent:
        result = await asyncio.wait_for(agent.run(prompt), timeout=REQUEST_TIMEOUT)
        text = getattr(result, "text", None)
        if text is None:
            text = str(result)
        return text.strip()
