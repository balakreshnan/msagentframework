import asyncio
import os
from agent_framework import ChatAgent
from agent_framework.azure import AzureAIAgentClient, AzureAISearchContextProvider
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def main():
    # Use managed identity for secure, keyless authentication
    credential = DefaultAzureCredential()

    async with (
        # Connect to Foundry IQ Knowledge Base for agentic retrieval
        AzureAISearchContextProvider(
            endpoint="https://stdagentvecstore.search.windows.net",
            knowledge_base_name="rfpdocs",
            credential=credential,
            mode="agentic",
        ) as search,
        # Connect to Azure AI Foundry for model inference
        AzureAIAgentClient(
            project_endpoint=os.getenv("AZURE_AI_PROJECT"),
            model_deployment_name=os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
            async_credential=credential,
        ) as client,
        # Create an agent grounded in your Knowledge Base
        ChatAgent(chat_client=client, context_providers=[search]) as agent,
    ):
        print((await agent.run("What's in the knowledge base?")).text)

asyncio.run(main())