import asyncio
import datetime
import os
from random import randint
from typing import Annotated
import re
import aiohttp
import pysmartthings
import json

from agent_framework.azure import AzureAIProjectAgentProvider
from azure.ai.projects.aio import AIProjectClient
from azure.ai.projects.models import AgentReference, PromptAgentDefinition
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from pydantic import Field

from dotenv import load_dotenv
# Load environment variables
load_dotenv()

TOKEN = os.getenv("SAMSUNG_PAT")
myEndpoint = os.getenv("AZURE_AI_PROJECT")

async def get_devices():
    """Get all SmartThings devices"""
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
            
            for comp_id, comp in d.components.items():
                caps = sorted([c for c in comp.capabilities])
                device_info["components"][comp_id] = {
                    "capabilities": caps
                }
            
            device_list.append(device_info)
        
        return device_list
    
def _convert_to_serializable(obj):
    """Convert pysmartthings objects to JSON-serializable types"""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _convert_to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_convert_to_serializable(item) for item in obj]
    if hasattr(obj, 'to_dict'):
        try:
            return _convert_to_serializable(obj.to_dict())
        except TypeError:
            # If to_dict() doesn't work, try without arguments
            try:
                return _convert_to_serializable(obj.to_dict())
            except:
                pass
    if hasattr(obj, '__dict__'):
        return _convert_to_serializable(vars(obj))
    # Fallback: convert to string
    return str(obj)

async def get_device_logs(device_id: str):
    """Get detailed logs and status for a specific device"""
    async with aiohttp.ClientSession() as session:
        api = pysmartthings.SmartThings(session=session, _token=TOKEN)
        device = await api.get_device(device_id)
        
        if not device:
            return {
                "success": False,
                "error": f"Device {device_id} not found"
            }
        
        # Get device status separately
        device_status = await api.get_device_status(device_id)
        # Convert to serializable format
        device_status_serializable = _convert_to_serializable(device_status)
        
        device_info = {
            "device_id": device.device_id,
            "label": device.label,
            "name": device.name,
            "type": str(device.type) if device.type else None,
            "location_id": device.location_id,
            "room_id": device.room_id,
            "components": {},
            "status": device_status_serializable
        }
        
        for comp_id, comp in device.components.items():
            capabilities = sorted([str(c) for c in comp.capabilities])
            device_info["components"][str(comp_id)] = {
                "capabilities": capabilities,
                "attributes": {}
            }
            
            # Get status for this component if available
            if comp_id in device_status:
                comp_status = device_status[comp_id]
                for capability in capabilities:
                    if capability in comp_status:
                        device_info["components"][str(comp_id)]["attributes"][str(capability)] = _convert_to_serializable(comp_status[capability])
        
        # Get device health
        try:
            device_health = await api.get_device_health(device_id)
            if device_health:
                device_info["health"] = {
                    "state": str(device_health.state) if hasattr(device_health, 'state') else str(device_health),
                }
        except Exception:
            pass
        
        result = {
            "success": True,
            "device": device_info,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return result

async def main(query: str)-> None:
    """
    This method creates a new agent version on the Azure AI service and returns
    a ChatAgent. Use this when you want to create a fresh agent with
    specific configuration.
    """
    print("=== provider.create_agent() Example ===")

    async with (
        DefaultAzureCredential() as credential,
        AzureAIProjectAgentProvider(credential=credential) as provider,
    ):
        # Create a new agent with custom configuration
        agent = await provider.create_agent(
            name="SmartthingsAgent",
            instructions="You are a helpful Samsung Smart things AI Agent. Always be concise. Also show device_id, name as output",
            description="An agent that provides information about home IoT devices.",
            tools=[ get_devices, get_device_logs]  # Assuming these tools are registered in the provider],
        )

        print(f"Created agent: {agent.name}")
        print(f"Agent ID: {agent.id}")

        #query = "View all my devices?"
        print(f"User: {query}")
        result = await agent.run(query)
        print(f"Agent: {result}\n")

    

if __name__ == "__main__":
    #rs = get_devices()
    #print(rs)
    #rs = asyncio.run(get_device_logs("a318f372-e660-1349-5ae1-427cd02ffd5e"))
    #print(rs)
    query = "View all my devices?"
    # query = "Give me the status of device with ID a318f372-e660-1349-5ae1-427cd02ffd5e?"
    asyncio.run(main(query))