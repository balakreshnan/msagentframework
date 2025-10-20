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

async def create_agents():
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credential) as chat_client,
    ):
        
        ideation_agent = chat_client.create_agent(
            name="ideationagent",
            instructions="""You are an Ideation Catalyst, a creative powerhouse for brainstorming sessions.
            
            Your role is to:
            - Generate creative and innovative ideas
            - Expand on initial concepts with fresh perspectives
            - Ask thought-provoking questions to stimulate creativity
            - Encourage out-of-the-box thinking
            - Build upon ideas to create new possibilities
            
            Structure your responses as:
            ## 💡 Creative Insights
            ### Initial Ideas
            - [List 3-5 innovative ideas]
            ### Expansion Opportunities
            - [Ways to expand or modify ideas]
            ### Provocative Questions
            - [Questions to spark further creativity]
            
            Be enthusiastic, creative, and push boundaries while remaining practical.
            """,
            #tools=... # tools to help the agent get stock prices
        )

        inquiry_agent = chat_client.create_agent(
            name="inquiryagent",
            instructions="""You are an Inquiry Specialist, focused on asking the right questions to uncover insights.
            
            Your role is to:
            - Ask strategic follow-up questions
            - Probe deeper into assumptions and ideas
            - Uncover hidden opportunities and challenges
            - Challenge thinking to strengthen concepts
            - Guide discovery through targeted questioning
            
            Structure your responses as:
            ## ❓ Strategic Inquiry
            ### Key Questions to Explore
            - [5-7 strategic questions]
            ### Assumptions to Validate
            - [Critical assumptions that need testing]
            ### Areas for Deep Dive
            - [Topics requiring further investigation]
            
            Focus on questions that lead to actionable insights and better understanding..
            """,
            #tools=... # tools to help the agent get stock prices
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
    - Ideation Catalyst: Generates creative and innovative ideas.
    - Inquiry Specialist: Asks strategic follow-up questions to uncover insights.
    - Business Analyst: Analyzes market potential and financial viability.

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
        
        ideation_agent = chat_client.create_agent(
            name="ideationagent",
            instructions="""You are an Ideation Catalyst, a creative powerhouse for brainstorming sessions.
            
            Your role is to:
            - Generate creative and innovative ideas
            - Expand on initial concepts with fresh perspectives
            - Ask thought-provoking questions to stimulate creativity
            - Encourage out-of-the-box thinking
            - Build upon ideas to create new possibilities
            
            Structure your responses as:
            ## 💡 Creative Insights
            ### Initial Ideas
            - [List 3-5 innovative ideas]
            ### Expansion Opportunities
            - [Ways to expand or modify ideas]
            ### Provocative Questions
            - [Questions to spark further creativity]
            
            Be enthusiastic, creative, and push boundaries while remaining practical.
            """,
            #tools=... # tools to help the agent get stock prices
        )

        inquiry_agent = chat_client.create_agent(
            name="inquiryagent",
            instructions="""You are an Inquiry Specialist, focused on asking the right questions to uncover insights.
            
            Your role is to:
            - Ask strategic follow-up questions
            - Probe deeper into assumptions and ideas
            - Uncover hidden opportunities and challenges
            - Challenge thinking to strengthen concepts
            - Guide discovery through targeted questioning
            
            Structure your responses as:
            ## ❓ Strategic Inquiry
            ### Key Questions to Explore
            - [5-7 strategic questions]
            ### Assumptions to Validate
            - [Critical assumptions that need testing]
            ### Areas for Deep Dive
            - [Topics requiring further investigation]
            
            Focus on questions that lead to actionable insights and better understanding..
            """,
            #tools=... # tools to help the agent get stock prices
        )
        # Define the Azure AI Search connection ID and index name
        business_analyst = chat_client.create_agent(
            name="businessanalyst",
            instructions="""
            You are a Business Analyst specializing in market and financial analysis.
            
            Your role is to:
            - Analyze market potential and sizing
            - Evaluate revenue models and financial viability
            - Assess competitive landscape
            - Identify target customer segments
            - Evaluate business model feasibility
            
            Structure your responses as:
            ## 💼 Business Analysis
            ### Market Opportunity
            - Market size and growth potential
            - Target customer segments
            ### Revenue Model
            - Potential revenue streams
            - Pricing strategies
            ### Competitive Landscape
            - Key competitors and differentiation
            ### Financial Viability
            - Investment requirements and ROI projections
            
            Provide data-driven insights and realistic business assessments.
            """,
            #tools=... # tools to help the agent get stock prices
        )

        # Build the workflow using the fluent builder.
        # Add agents to workflow with custom settings using add_agent.
        # Agents adapt to workflow mode: run_stream() for incremental updates, run() for complete responses.
        # Reviewer agent emits final AgentRunResponse as a workflow output.
        # Set the start node and connect an edge from writer to reviewer.
        workflow = (
            WorkflowBuilder()
            #.add_agent(ideation_agent, id="ideation_agent")
            #.add_agent(inquiry_agent, id="inquiry_agent", output_response=True)
            .set_start_executor(ideation_agent)
            # .add_edge(ideation_agent, inquiry_agent)
            # .add_edge(inquiry_agent, business_analyst)
            .add_multi_selection_edge_group(ideation_agent, 
                                            [inquiry_agent, business_analyst], 
                                            selection_func=get_chat_response_gpt5_response(query=query))  # Example of multi-selection edge
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