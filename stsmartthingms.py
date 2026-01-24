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
from azure.identity.aio import AzureCliCredential
from pydantic import Field

from dotenv import load_dotenv
# Load environment variables
load_dotenv()

TOKEN = os.getenv("SAMSUNG_PAT")
myEndpoint = os.getenv("AZURE_AI_PROJECT")

async def async_get_devices():
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

def get_devices():
    """Synchronous wrapper — not recommended but works in simple scripts"""
    return asyncio.run(async_get_devices())
    
def async_get_device_logs(device_id: str):
    """Get detailed logs and status for a specific device"""
    with aiohttp.ClientSession() as session:
        api = pysmartthings.SmartThings(session=session, _token=TOKEN)
        device = api.get_device(device_id)
        
        if not device:
            return {
                "success": False,
                "error": f"Device {device_id} not found"
            }
        
        device.status.refresh()
        
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
        
        for comp_id, comp in device.components.items():
            capabilities = sorted([c for c in comp.capabilities])
            device_info["components"][comp_id] = {
                "capabilities": capabilities,
                "attributes": {}
            }
            
            if hasattr(device.status, comp_id):
                comp_status = getattr(device.status, comp_id)
                
                for capability in capabilities:
                    if hasattr(comp_status, capability):
                        attr_value = getattr(comp_status, capability)
                        device_info["components"][comp_id]["attributes"][capability] = {
                            "value": str(attr_value) if attr_value is not None else None
                        }
        
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

def get_device_logs(device_id: str):
    """Synchronous wrapper — not recommended but works in simple scripts"""
    return asyncio.run(async_get_device_logs(device_id))

if __name__ == "__main__":
    rs = get_devices()
    print(rs)