import asyncio
from contextlib import AsyncExitStack
import os
import json
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Annotated, Dict, List, Any
from openai import AzureOpenAI
import requests
import streamlit as st
from utils import get_weather, fetch_stock_data

from agent_framework import ChatAgent, ChatMessage, ai_function
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import get_tracer, setup_observability
from pydantic import Field
from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowOutputEvent, SequentialBuilder
from typing import Final

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    executor,
)

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add Microsoft Learn MCP tool
mcplearn = HostedMCPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        approval_mode='never_require'
    )

hfmcp = HostedMCPTool(
        name="HuggingFace MCP",
        url="https://huggingface.co/mcp",
        # approval_mode='always_require'  # for testing approval flow
        approval_mode='never_require'
    )

def normalize_token_usage(usage) -> dict:
    """Normalize various usage objects/dicts into a standard dict.
    Returns {'prompt_tokens', 'completion_tokens', 'total_tokens'} or {} if unavailable.
    """
    try:
        if not usage:
            return {}
        # If it's already a dict, use it directly
        if isinstance(usage, dict):
            d = usage
        else:
            # Attempt attribute access (e.g., ResponseUsage pydantic model)
            d = {}
            for name in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
                val = getattr(usage, name, None)
                if val is not None:
                    d[name] = val

        prompt = int(d.get("prompt_tokens", d.get("input_tokens", 0)) or 0)
        completion = int(d.get("completion_tokens", d.get("output_tokens", 0)) or 0)
        total = int(d.get("total_tokens", prompt + completion) or 0)
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}
    except Exception:
        return {}

@ai_function
def load_chiprca_csv_files() -> str:
    tools = ""
    data_folder = Path("./data")
    for csv_file in data_folder.glob("chiprca_*.csv"):
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
            tools += f"Contents of {csv_file.name}:\n{content}\n\n"
    return tools
    
async def multi_agent_interaction(query: str) -> str:
    returntxt = ""
    stack = AsyncExitStack()
    
    try:
        deployment = "gpt-5-chat-2"
        # deployment = "gpt-4o"
        
        # Properly manage async context with AsyncExitStack
        credential = await stack.enter_async_context(AzureCliCredential())
        project_client = await stack.enter_async_context(
            AIProjectClient(
                endpoint=os.environ["AZURE_AI_PROJECT"], 
                credential=credential
            )
        )
        
        async with (
            AzureCliCredential() as credential,
            AzureAIAgentClient(credential=credential, 
                            project_client=project_client,
                            model_deployment_name=deployment
                            ) as chat_client,
        ):
        
            await chat_client.setup_azure_ai_observability()

            with get_tracer().start_as_current_span("ChipRCA", kind=SpanKind.CLIENT) as current_span:
                print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
                
                # Create RCA agent - Remove 'name' parameter, use client instead
                rca_agent = chat_client.create_agent(
                    name="ChipRCAAgent",
                    instructions="You are a root cause analysis expert. Use the tools to answer the query.",
                    # Don't use 'name' parameter with ChatAgent
                    tools=[load_chiprca_csv_files],
                )

                # Create ISO9001 agent - use chat_client.create_agent for second agent
                iso9001_agent = chat_client.create_agent(
                    name="ISO9001Agent",
                    instructions="""Use your knowledge of ISO 9001 standards to ensure quality management practices are followed.
                    Make sure to reference relevant ISO 9001 clauses when providing recommendations.
                    use the data from the RCA agent to create the report.
                    Report should be in ISO 9001 format.
                    """,
                )
                
                workflow = (
                    WorkflowBuilder()
                    .set_start_executor(rca_agent)
                    .add_edge(rca_agent, iso9001_agent)
                    .build()
                )

                # Stream events from the workflow
                last_executor_id: str | None = None
                
                try:
                    events = workflow.run_stream(query)
                    async for event in events:
                        if isinstance(event, AgentRunUpdateEvent):
                            eid = event.executor_id
                            if eid != last_executor_id:
                                if last_executor_id is not None:
                                    print()
                                print(f"{eid}:", end=" ", flush=True)
                                last_executor_id = eid
                            print(event.data, end="", flush=True)
                        elif isinstance(event, WorkflowOutputEvent):
                            print("\n===== Final output =====")
                            print(event.data)
                            returntxt = event.data
                except Exception as e:
                    print(f"Error during workflow execution: {e}")
                    returntxt = f"Workflow error: {str(e)}"

    except Exception as e:
        print(f"Error during multi-agent interaction: {e}")
        returntxt = f"Error during multi-agent interaction: {str(e)}"
    finally:
        # Ensure all async resources are properly closed
        await stack.aclose()
        # Give time for cleanup on Windows
        await asyncio.sleep(0.25)
    
    return returntxt

if __name__ == "__main__":
    #asyncio.run(create_agents())
    # query = "Create me a catchy phrase for humanoid enabling better remote work."
    query = "Create a RCA analysis on the issues and create a ISO report."
    try:
        returntxt = asyncio.run(multi_agent_interaction(query))
        print("output:", returntxt)
    except Exception as e:
        print(f"Error during multi-agent interaction: {e}")
        pass