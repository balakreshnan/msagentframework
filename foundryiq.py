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
            endpoint="https://vecdb.search.windows.net",
            knowledge_base_name="constructionrfpdocs1",
            credential=credential,
            mode="agentic",
            azure_openai_resource_url=os.getenv("AZURE_OPENAI_ENDPOINT_BASIC"),  # Azure OpenAI only
            model_deployment_name="gpt-4o",
            retrieval_reasoning_effort="medium",  # Full query planning
        ) as search,
        # Connect to Azure AI Foundry for model inference
        AzureAIAgentClient(
            project_endpoint=os.getenv("AZURE_AI_PROJECT_BASIC"),
            model_deployment_name=os.getenv("AZURE_OPENAI_DEPLOYMENT_BASIC"),
            credential=credential,
        ) as client,
        # Create an agent grounded in your Knowledge Base
        ChatAgent(chat_client=client, context_providers=[search]) as agent,
    ):
        print((await agent.run("What's in the knowledge base?")).text)

asyncio.run(main())