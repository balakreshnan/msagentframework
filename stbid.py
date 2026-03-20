import asyncio
import base64
import html as html_lib
import json
import logging
import os
import re
import time as _time
import traceback
from typing import cast

import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI
from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Message,
    WorkflowEvent,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatRequestSentEvent, MagenticBuilder, MagenticProgressLedger
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework.azure import AzureAIProjectAgentProvider
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.ai.projects import AIProjectClient
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

myEndpoint = os.getenv("AZURE_AI_PROJECT")

client = AzureOpenAIResponsesClient(
    project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    credential=DefaultAzureCredential(),
)

async def bidding(query: str):
    walmart_agent = Agent(
        name="walmart_agent",
        description="Provide product and price information to agents.",
        instructions=(
            """You are a Retail Walmart Agent. Provide real-time product and price information to agents. 
            Also provide available quantity and shipping information. 
            If you don't know the answer, say you don't know. 
            Always provide the most accurate and up-to-date information. Be concise and to the point.
            """
        ),
        client=client,
    )

    amazon_agent = Agent(
        name="amazon_agent",
        description="Provide product and price information to agents.",
        instructions=(
            """You are a Retail Amazon Agent. Provide real-time product and price information to agents. 
            Also provide available quantity and shipping information. 
            If you don't know the answer, say you don't know. 
            Always provide the most accurate and up-to-date information. Be concise and to the point.
            """
        ),
        client=client,
    )

    bidding_agent = Agent(
        name="bidding_agent",
        description="Bid all agents and find the best deals.",
        instructions=(
            """You are a Retail Bidding Agent. Get the product and price, quantity from vendor agents. 
            Compare the prices, quantity and shipping information and find the best deal for the user.
            If you don't know the answer, say you don't know. 
            Find the best deal and provide it to the user. Be concise and to the point.
            """
        ),
        client=client,
    )

    # Create a manager agent for orchestration
    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates the walmart, amazon, and bidding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        client=client,
    )

    # Create a MagenticBuilder to define the workflow
    workflow = MagenticBuilder(
        participants=[walmart_agent, amazon_agent, bidding_agent],
        intermediate_outputs=True,
        manager_agent=manager_agent,
        max_round_count=10,
        max_stall_count=3,
        max_reset_count=2,
    ).build()

    last_response_id: str | None = None
    output_event: WorkflowEvent | None = None
    current_agent_text = ""
    current_agent_name = ""

    task = query

    # Keep track of the last executor to format output nicely in streaming mode
    last_message_id: str | None = None
    output_event: WorkflowEvent | None = None
    async for event in workflow.run(task, stream=True):
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            message_id = event.data.message_id
            if message_id != last_message_id:
                if last_message_id is not None:
                    print("\n")
                print(f"- {event.executor_id}:", end=" ", flush=True)
                last_message_id = message_id
            print(event.data, end="", flush=True)

        elif event.type == "magentic_orchestrator":
            print(f"\n[Magentic Orchestrator Event] Type: {event.data.event_type.name}")
            if isinstance(event.data.content, Message):
                print(f"Please review the plan:\n{event.data.content.text}")
            elif isinstance(event.data.content, MagenticProgressLedger):
                print(f"Please review progress ledger:\n{json.dumps(event.data.content.to_dict(), indent=2)}")
            else:
                print(f"Unknown data type in MagenticOrchestratorEvent: {type(event.data.content)}")

            # Block to allow user to read the plan/progress before continuing
            # Note: this is for demonstration only and is not the recommended way to handle human interaction.
            # Please refer to `with_plan_review` for proper human interaction during planning phases.
            await asyncio.get_event_loop().run_in_executor(None, input, "Press Enter to continue...")

        elif event.type == "output":
            output_event = event

    # The output of the Magentic workflow is a list of ChatMessages with only one final message
    # generated by the orchestrator.
    output_messages = cast(list[Message], output_event.data)
    output = output_messages[-1].text
    print(output)

if __name__ == "__main__":
    query = "i am looking for 1 dozen of fresh strawberries?"
    asyncio.run(bidding(query))