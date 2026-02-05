import asyncio
import logging
import os
import time

# Core Agent Framework types
from agent_framework import ChatAgent

# Azure AI / Foundry chat client integration
from agent_framework.azure import AzureAIAgentClient
from dotenv import load_dotenv
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from pydantic import Field
from azure.identity.aio import DefaultAzureCredential

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

myEndpoint = os.getenv("AZURE_AI_PROJECT")
deployment_name = "Kimi-K2.5"

async def main():
    credential = DefaultAzureCredential()
    
    async with AzureAIAgentClient(
        project_endpoint=myEndpoint,
        model_deployment_name=deployment_name,
        credential=credential,
    ) as chat_client:

        # Agent 1: "Research" persona
        researcher = ChatAgent(
            chat_client=chat_client,
            name="researcher",
            instructions=(
                "You are a research agent. Produce concise bullet points with key facts, "
                "assumptions, and risks. If information is missing, list what you'd need."
            ),
        )

        # Agent 2: "Writer" persona
        writer = ChatAgent(
            chat_client=chat_client,
            name="writer",
            instructions=(
                "You are a writing agent. Produce a clear, well-structured answer with headings, "
                "and a short executive summary at the top."
            ),
        )

        user_prompt = (
            "Design a reference architecture for a multi-agent system on Azure AI Foundry "
            "that uses a reasoning model and supports tool calling. Keep it practical."
        )

        # Run BOTH agents at the same time with timing
        async def timed_run(agent, prompt, name):
            print(f"Starting time {name} agent... {time.strftime('%Y-%m-%d %H:%M:%S')}")
            start = time.perf_counter()
            result = await agent.run(prompt)
            elapsed = time.perf_counter() - start
            print(f"{name} agent finished in {elapsed:.2f}s")
            return result, elapsed, name

        research_task = timed_run(researcher, user_prompt, "Researcher")
        writing_task = timed_run(writer, user_prompt, "Writer")

        (research_result, research_time, _), (writing_result, writing_time, _) = await asyncio.gather(
            research_task, writing_task
        )

        # The result object shape can vary by version; commonly you'll have .text or messages.
        research_text = getattr(research_result, "text", str(research_result))
        writing_text = getattr(writing_result, "text", str(writing_result))

        # Simple "fan-in" aggregation
        final = f"""# Execution Times
- Researcher Agent: {research_time:.2f}s
- Writer Agent: {writing_time:.2f}s

# Executive Summary (Writer)

{writing_text}

---

# Key Facts / Risks (Researcher)

{research_text}
"""

        print(final)


if __name__ == "__main__":
    asyncio.run(main())
