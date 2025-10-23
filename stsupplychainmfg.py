import asyncio
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

from agent_framework import ChatAgent, ChatMessage
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import get_tracer, setup_observability
from pydantic import Field
from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowOutputEvent
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

def get_chat_response_gpt5_response(query: str) -> str:
    returntxt = ""

    responseclient = AzureOpenAI(
        base_url = os.getenv("AZURE_OPENAI_ENDPOINT") + "/openai/v1/",  
        api_key= os.getenv("AZURE_OPENAI_KEY"),
        api_version="preview"
        )
    deployment = "gpt-5"

    prompt = """You are a brainstorming assistant. Given the following query, 
    provide creative ideas and suggestions.
    Here are the agents available to you:
    - supplychainmonitoragent: Monitors supply chain data and identifies anomalies.
    - disruptionpredictionagent: Predicts potential supply chain disruptions.   
    - scenariosimulationagent: Simulates alternative sourcing scenarios.
    - inventoryoptimizationagent: Optimizes inventory levels across facilities.

    Based on the query, pick the most relevant agents to assist you in brainstorming.
    Query: {query}
    
    Respond only the agents to use as array of strings.
    """

    # Some new parameters!  
    response = responseclient.responses.create(
        input=prompt.format(query=query),
        model=deployment,
        reasoning={
            "effort": "medium",
            "summary": "auto" # auto, concise, or detailed 
        },
        text={
            "verbosity": "low" # New with GPT-5 models
        }
    )

    # # Token usage details
    usage = normalize_token_usage(response.usage)

    # print("--------------------------------")
    # print("Output:")
    # print(output_text)
    returntxt = response.output_text

    return returntxt, usage

async def multi_agent_interaction(query: str) -> str:
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential) as chat_client,
    ):
        
        supplychainmonitoragent = chat_client.create_agent(
            name="supplychainmonitoragent",
            instructions="""Continuously collect and analyze data from various tiers of the supply chain. 
        Identify anomalies and report status updates.
            """,
            #tools=... # tools to help the agent get stock prices
        )

        disruptionpredictionagent = chat_client.create_agent(
            name="disruptionpredictionagent",
            instructions="""Use historical and real-time data to forecast potential disruptions. 
        Provide risk scores and mitigation suggestions.
            """,
            #tools=... # tools to help the agent get stock prices
        )

        scenariosimulationagent = chat_client.create_agent(
            name="scenariosimulationagent",
            instructions="""Generate and evaluate alternative sourcing scenarios based on current supply chain data and predicted disruptions.
            """,
            #tools=... # tools to help the agent get stock prices
        )

        inventoryoptimizationagent = chat_client.create_agent(
            name="inventoryoptimizationagent",
            instructions="""Analyze inventory levels across global facilities and recommend adjustments to maintain resilience and efficiency.
            """,
            #tools=... # tools to help the agent get stock prices
        )
        workflow = (
            WorkflowBuilder()
            #.add_agent(ideation_agent, id="ideation_agent")
            #.add_agent(inquiry_agent, id="inquiry_agent", output_response=True)
            .set_start_executor(supplychainmonitoragent)
            .add_edge(supplychainmonitoragent, disruptionpredictionagent)
            .add_edge(disruptionpredictionagent, scenariosimulationagent)
            .add_edge(scenariosimulationagent, inventoryoptimizationagent)
            # .add_multi_selection_edge_group(supplychainmonitoragent, 
            #                                 [disruptionpredictionagent, 
            #                                  scenariosimulationagent, 
            #                                  inventoryoptimizationagent], 
            #                                 selection_func=get_chat_response_gpt5_response(query=query))  # Example of multi-selection edge
            .build()
        )

        # Stream events from the workflow. We aggregate partial token updates per executor for readable output.
        last_executor_id: str | None = None

        events = workflow.run_stream(query)
        async for event in events:
            if isinstance(event, AgentRunUpdateEvent):
                # AgentRunUpdateEvent contains incremental text deltas from the underlying agent.
                # Print a prefix when the executor changes, then append updates on the same line.
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

        #chat_client.delete_agent(ideation_agent.id)
        #chat_client.delete_agent(inquiry_agent.id)
        # await chat_client.project_client.agents.delete_agent(ideation_agent.id)
        # await chat_client.project_client.agents.delete_agent(inquiry_agent.id)
        # chat_client.project_client.agents.threads.delete(ideation_agent.id)

    return "Done"

if __name__ == "__main__":
    #asyncio.run(create_agents())
    # query = "Create me a catchy phrase for humanoid enabling better remote work."
    query = "Create a AI Data center to handle 1GW capacity with 10MW power usage effectiveness.With 250000 GPU's."
    asyncio.run(multi_agent_interaction(query))