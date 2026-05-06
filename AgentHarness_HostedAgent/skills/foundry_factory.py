"""Foundry-backed factory for one-shot Agent runs.

The adversarial test agent, the business agent and the judge are all just
`Agent(FoundryChatClient(...), instructions=...)`. They differ only in the
system prompt + which Foundry deployment they bind to.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential

from .config import PROJECT_ENDPOINT, REQUEST_TIMEOUT


@asynccontextmanager
async def make_agent(
    deployment: str,
    instructions: str,
    name: str,
) -> AsyncIterator[Agent]:
    """Yield a ready-to-use Agent backed by a Foundry deployment."""
    if not PROJECT_ENDPOINT:
        raise RuntimeError(
            "Set FOUNDRY_PROJECT_ENDPOINT in your .env (Microsoft Foundry project endpoint)."
        )
    async with DefaultAzureCredential() as credential:
        client = FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=deployment,
            credential=credential,
            allow_preview=True,
        )
        agent = Agent(
            client,
            instructions=instructions,
            name=name,
        )
        yield agent


async def run_once(deployment: str, instructions: str, name: str, prompt: str) -> str:
    import asyncio

    async with make_agent(deployment, instructions, name) as agent:
        result = await asyncio.wait_for(agent.run(prompt), timeout=REQUEST_TIMEOUT)
        # Agent.run returns an AgentRunResponse; prefer .text, fall back to str().
        text = getattr(result, "text", None)
        if text is None:
            text = str(result)
        return text.strip()
