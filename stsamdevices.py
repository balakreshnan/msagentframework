
import asyncio
import re
import aiohttp
import pysmartthings
import os
import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Annotated, Dict, List, Any
import requests
import streamlit as st
from utils import get_weather, fetch_stock_data
import io
import sys
import time

from agent_framework import ChatAgent, ChatMessage
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework import observability
from pydantic import Field
from azure.ai.agents.models import FileInfo, VectorStore
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType
from azure.ai.projects.models import ConnectionType
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TOKEN = os.getenv("SAMSUNG_PAT")
myEndpoint = os.getenv("AZURE_AI_PROJECT")

async def getdevices():
    async with aiohttp.ClientSession() as session:
        api = pysmartthings.SmartThings(session=session, _token=TOKEN)

        devices = await api.get_devices()
        device_list = []
        
        for d in devices:
            device_info = {
                "device_id": d.device_id,
                "label": d.label,
                "name": d.name,
                "type": d.type,
                "components": {}
            }
            
            # Components and capabilities
            for comp_id, comp in d.components.items():
                caps = sorted([c for c in comp.capabilities])
                device_info["components"][comp_id] = {
                    "capabilities": caps
                }
            
            device_list.append(device_info)
        
        return device_list

async def get_device_logs(device_id: str):
    """Get detailed logs and status for a specific device"""
    async with aiohttp.ClientSession() as session:
        api = pysmartthings.SmartThings(session=session, _token=TOKEN)
        
        # Get device details
        device = await api.get_device(device_id)
        
        if not device:
            return {
                "success": False,
                "error": f"Device {device_id} not found"
            }
        
        # Get device status
        await device.status.refresh()
        
        # Compile device information
        device_info = {
            "device_id": device.device_id,
            "label": device.label,
            "name": device.name,
            "type": device.type,
            "location_id": device.location_id,
            "room_id": device.room_id,
            "components": {},
            "status": {}
        }
        
        # Get component details with current status
        for comp_id, comp in device.components.items():
            capabilities = sorted([c for c in comp.capabilities])
            device_info["components"][comp_id] = {
                "capabilities": capabilities,
                "attributes": {}
            }
            
            # Get current attribute values for this component
            if hasattr(device.status, comp_id):
                comp_status = getattr(device.status, comp_id)
                
                # Extract all attributes from the component status
                for capability in capabilities:
                    # Try to get attribute value
                    if hasattr(comp_status, capability):
                        attr_value = getattr(comp_status, capability)
                        device_info["components"][comp_id]["attributes"][capability] = {
                            "value": str(attr_value) if attr_value is not None else None
                        }
        
        # Get device health status if available
        if hasattr(device, 'health'):
            device_info["health"] = {
                "state": device.health.state if hasattr(device.health, 'state') else None,
                "last_updated": device.health.last_updated_date if hasattr(device.health, 'last_updated_date') else None
            }
        
        result = {
            "success": True,
            "device": device_info,
            "timestamp": datetime.now().isoformat()
        }
        
        return result

def agent_main(query: str):
    #setup_observability()
    # tracer = observability.get_tracer()
    from agent_framework import tool
    
    # Define SmartThings tools
    @tool
    async def get_smartthings_devices() -> List[Dict[str, Any]]:
        """Get all Samsung SmartThings devices with their components and capabilities.
        
        Returns:
            List of devices with their details including device_id, label, name, type, and components with capabilities.
        """
        return await getdevices()
    
    @tool
    async def get_smartthings_device_logs(device_id: str) -> Dict[str, Any]:
        """Get detailed status, events, and logs for a specific Samsung SmartThings device.
        
        Args:
            device_id: The device ID to get logs for
            
        Returns:
            Detailed device information including current status, component attributes, and health status.
        """
        return await get_device_logs(device_id)
    
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )

    def extract_response_text(raw):
        raw = str(raw)   # <-- ensure it's always a string
        m = re.search(r"ResponseOutputText\(.*?text='([^']+)'", raw, re.DOTALL)
        return m.group(1) if m else None


    myAgent = "smartthingsagent"
    with observability.get_tracer().start_as_current_span("smartthingsagent", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
        # Get an existing agent
        agent = project_client.agents.get(agent_name=myAgent)
        print(f"Retrieved agent: {agent.name}")
        
        # Add SmartThings tools to the agent
        if hasattr(agent, 'tools'):
            agent.tools = agent.tools + [get_smartthings_devices, get_smartthings_device_logs]
        else:
            agent.tools = [get_smartthings_devices, get_smartthings_device_logs]
        print(f"Added SmartThings tools to agent")

        openai_client = project_client.get_openai_client()

        # Reference the agent to get a response
        response = openai_client.responses.create(
            input=[{"role": "user", "content": "Summarize the RFP for virginia Railway Express project?"}],
            extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
        )

        print("Initial Response Status:", response.status)
        print("Response ID:", response.id)
        print("\n" + "="*80 + "\n")

        # Check if there are MCP approval requests
        mcp_approval_requests = []
        for output_item in response.output:
            if hasattr(output_item, 'type') and output_item.type == 'mcp_approval_request':
                mcp_approval_requests.append(output_item)
                print(f"MCP Approval Request Found:")
                print(f"  - ID: {output_item.id}")
                print(f"  - Tool: {output_item.name}")
                print(f"  - Server: {output_item.server_label}")
                print(f"  - Arguments: {output_item.arguments}")
                print()

        # Auto-approve all MCP tool calls
        if mcp_approval_requests:
            print(f"Auto-approving {len(mcp_approval_requests)} MCP tool call(s)...\n")
            
            # Approve each MCP request by creating a new response with approval
            for approval_request in mcp_approval_requests:
                response = openai_client.responses.create(
                    previous_response_id=response.id,
                    input=[{
                        "type": "mcp_approval_response",
                        "approve": True,
                        "approval_request_id": approval_request.id
                    }],
                    extra_body={"agent": {"name": agent.name, "type": "agent_reference"}}
                )
                print(f"✓ Approved: {approval_request.name}")
            
            print("\n" + "="*80 + "\n")
            print("Waiting for final response...\n")
            
            # Poll for the final result
            import time
            max_retries = 30
            retry_count = 0
            
            while retry_count < max_retries:
                response = openai_client.responses.retrieve(response_id=response.id)
                
                if response.status == 'completed':
                    print("Response completed!")
                    # print('Result:', response)
                    break
                elif response.status == 'failed':
                    print("Response failed!")
                    if response.error:
                        print(f"Error: {response.error}")
                    break
                else:
                    print(f"Status: {response.status} - waiting...")
                    time.sleep(2)
                    retry_count += 1
            
            print("\n" + "="*80 + "\n")

        # Display the final result with citations
        print("FINAL RESPONSE:")
        print("="*80)

        for output_item in response.output:
            item_type = getattr(output_item, 'type', None)
            
            # Check for message output (ResponseOutputMessage)
            if item_type == 'message':
                print("\n📄 Response Text:")
                if hasattr(output_item, 'content') and output_item.content:
                    for content_item in output_item.content:
                        if hasattr(content_item, 'text'):
                            print(content_item.text)
                            print()
                            
                            # Display citations if available
                            if hasattr(content_item, 'annotations') and content_item.annotations:
                                print("\n📚 Citations:")
                                for i, annotation in enumerate(content_item.annotations, 1):
                                    print(f"\n  [{i}] {annotation.text if hasattr(annotation, 'text') else 'Citation'}")
                                    if hasattr(annotation, 'file_citation'):
                                        citation = annotation.file_citation
                                        print(f"      Source: {citation.file_name if hasattr(citation, 'file_name') else 'N/A'}")
                                        if hasattr(citation, 'quote'):
                                            print(f"      Quote: {citation.quote}")
            
            # Check for direct text output (older format)
            elif item_type == 'response_output_text':
                print("\n📄 Response Text:")
                print(output_item.text)
                print()
                
                # Display citations if available
                if hasattr(output_item, 'annotations') and output_item.annotations:
                    print("\n📚 Citations:")
                    for i, annotation in enumerate(output_item.annotations, 1):
                        print(f"\n  [{i}] {annotation.text if hasattr(annotation, 'text') else 'Citation'}")
                        if hasattr(annotation, 'file_citation'):
                            citation = annotation.file_citation
                            print(f"      Source: {citation.file_name if hasattr(citation, 'file_name') else 'N/A'}")
                            if hasattr(citation, 'quote'):
                                print(f"      Quote: {citation.quote}")
            
            # Check for MCP call results
            elif item_type == 'mcp_call':
                print("\n🔧 MCP Tool Call:")
                print(f"  Tool: {output_item.name}")
                print(f"  Status: {output_item.status}")
                if hasattr(output_item, 'output') and output_item.output:
                    # Limit output display to avoid clutter
                    output_text = str(output_item.output)
                    if len(output_text) > 500:
                        print(f"  Output: {output_text[:500]}... (truncated)")
                    else:
                        print(f"  Output: {output_text}")
                print()

        print("\n" + "="*80)
    print("End of conversation with agent.")


async def main():
    """Main function - can test device listing or run the agent"""
    
    # Option 1: Simple device listing
    print("\n=== Device Listing ===")
    devices = await getdevices()
    print(f"\nFound {len(devices)} devices:\n")
    for device in devices:
        print(f"Device: {device['label']} (id={device['device_id']})")
        for comp_id, comp_data in device['components'].items():
            print(f"  Component: {comp_id}")
            print(f"    Capabilities: {', '.join(comp_data['capabilities'])}")
        print()
    
    # Option 2: Run agent with a query (uncomment to use)
    # print("\n=== Running SmartThings Agent ===")
    # await run_smartthings_agent("What SmartThings devices do I have?")
    # 
    # # Get logs for first device
    # if devices:
    #     first_device_id = devices[0]['device_id']
    #     await run_smartthings_agent(f"Show me detailed logs for device {first_device_id}")
        
asyncio.run(main())
