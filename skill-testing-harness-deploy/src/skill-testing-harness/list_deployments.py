import asyncio, os
from dotenv import load_dotenv
load_dotenv()
from azure.identity.aio import DefaultAzureCredential
from azure.ai.projects.aio import AIProjectClient


async def main():
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    async with DefaultAzureCredential() as cred:
        async with AIProjectClient(endpoint=endpoint, credential=cred) as proj:
            print("=== deployments ===")
            async for d in proj.deployments.list():
                print(getattr(d, "name", "?"), "|",
                      getattr(d, "type", "?"), "|",
                      getattr(d, "model_name", "?"), "|",
                      getattr(d, "model_publisher", "?"))


asyncio.run(main())
