import asyncio
import logging
import streamlit as st
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ResponseStreamEventType
from agent_framework import Content, Role
from agent_framework.azure import AzureAIAgentClient
from agent_framework.observability import get_tracer
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from pydantic import Field
import os
from dotenv import load_dotenv
from PIL import Image
import io
import base64
from datetime import datetime

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

myEndpoint = os.getenv("AZURE_AI_PROJECT")

def studentiq(query: str) -> str:
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )

    with project_client:

        workflow = {
            "name": "StudentIQ",
            "version": "1",
        }
        
        openai_client = project_client.get_openai_client()

        conversation = openai_client.conversations.create()
        print(f"Created conversation (id: {conversation.id})")

        stream = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent": {"name": workflow["name"], "type": "agent_reference"}},
            input=query,
            stream=True,
            metadata={"x-ms-debug-mode-enabled": "1"},
        )

        for event in stream:
            if event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DONE:
                print("\t", event.text)
            elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED and event.item.type == "workflow_action":
                print(f"********************************\nActor - '{event.item.action_id}' :")
            elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED and event.item.type == "workflow_action":
                print(f"Unknown event: {event}")

        openai_client.conversations.delete(conversation_id=conversation.id)
        print("Conversation deleted")

if __name__ == "__main__":
    studentiq("How to i create a agent in Microsoft Foundry?")