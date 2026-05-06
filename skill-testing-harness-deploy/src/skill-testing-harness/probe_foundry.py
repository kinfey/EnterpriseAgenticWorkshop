"""Minimal probe to isolate the FoundryChatClient connection error.

Runs `agent.run("ping")` against MODEL_GPT, prints either OK or the full
exception chain so we can tell whether it's DNS, auth, deployment-name, or
network-policy related.
"""
import asyncio
import os
import traceback

from dotenv import load_dotenv

load_dotenv()

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity.aio import DefaultAzureCredential


async def main() -> None:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    deployment = os.environ.get("MODEL_GPT", "gpt-5.5")
    print(f"endpoint   = {endpoint}")
    print(f"deployment = {deployment}")

    async with DefaultAzureCredential() as cred:
        # Quick auth check
        try:
            tok = await cred.get_token("https://ai.azure.com/.default")
            print(f"token len  = {len(tok.token)} (exp={tok.expires_on})")
        except Exception as e:  # noqa: BLE001
            print("TOKEN ERROR:")
            traceback.print_exc()
            return

        client = FoundryChatClient(
            project_endpoint=endpoint,
            model=deployment,
            credential=cred,
            allow_preview=True,
        )
        agent = Agent(client, instructions="You are helpful.", name="probe")
        try:
            r = await agent.run("ping")
            text = getattr(r, "text", None) or str(r)
            print("OK:", text[:200])
        except Exception:  # noqa: BLE001
            print("RUN ERROR:")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
