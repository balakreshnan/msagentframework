"""
Samsung SmartThings MCP Server
Local MCP server for interacting with Samsung SmartThings devices
Use this with the existing 'smartthingsagent' in Azure AI Foundry
"""
import asyncio
import aiohttp
import pysmartthings
import os
import json
from typing import Any, Dict, List
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Samsung PAT from environment
SAMSUNG_PAT = os.getenv("SAMSUNG_PAT")

# Try to import MCP - if not available, will run in standalone mode
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("MCP library not available. Install with: pip install mcp")

# Create MCP server instance
app = Server("samsung-smartthings")

# Global session and API client
_session: aiohttp.ClientSession | None = None
_api: pysmartthings.SmartThings | None = None


async def get_api() -> pysmartthings.SmartThings:
    """Get or create the SmartThings API client"""
    global _session, _api
    
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    
    if _api is None:
        _api = pysmartthings.SmartThings(session=_session, _token=SAMSUNG_PAT)
    
    return _api


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available SmartThings tools"""
    return [
        Tool(
            name="get_devices",
            description="Get all Samsung SmartThings devices with their components and capabilities",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_device_logs",
            description="Get detailed status, events, and logs for a specific Samsung SmartThings device",
            inputSchema={
                "type": "object",
                "properties": {
                    "device_id": {
                        "type": "string",
                        "description": "The device ID to get logs for"
                    }
                },
                "required": ["device_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool calls"""
    
    if name == "get_devices":
        return await get_devices_tool()
    elif name == "get_device_logs":
        device_id = arguments.get("device_id")
        if not device_id:
            return [TextContent(
                type="text",
                text=json.dumps({"error": "device_id is required"})
            )]
        return await get_device_logs_tool(device_id)
    else:
        return [TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]


async def get_devices_tool() -> list[TextContent]:
    """Get all SmartThings devices"""
    try:
        api = await get_api()
        devices = await api.get_devices()
        
        device_list = []
        for device in devices:
            device_info = {
                "device_id": device.device_id,
                "label": device.label,
                "name": device.name,
                "type": device.type,
                "components": {}
            }
            
            # Get components and capabilities
            for comp_id, comp in device.components.items():
                capabilities = sorted([c for c in comp.capabilities])
                device_info["components"][comp_id] = {
                    "capabilities": capabilities
                }
            
            device_list.append(device_info)
        
        result = {
            "success": True,
            "device_count": len(device_list),
            "devices": device_list
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__
            })
        )]


async def get_device_logs_tool(device_id: str) -> list[TextContent]:
    """Get detailed logs and status for a specific device"""
    try:
        api = await get_api()
        
        # Get device details
        device = await api.get_device(device_id)
        
        if not device:
            return [TextContent(
                type="text",
                text=json.dumps({
                    "success": False,
                    "error": f"Device {device_id} not found"
                })
            )]
        
        # Get device status
        status = await device.status.refresh()
        
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
            "timestamp": asyncio.get_event_loop().time()
        }
        
        return [TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
        
    except Exception as e:
        return [TextContent(
            type="text",
            text=json.dumps({
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
                "device_id": device_id
            })
        )]


async def cleanup():
    """Cleanup resources"""
    global _session, _api
    
    _api = None
    if _session and not _session.closed:
        await _session.close()
    _session = None


async def main():
    """Main entry point for the MCP server"""
    if not MCP_AVAILABLE:
        print("Error: MCP library not installed. Install with: pip install mcp")
        return
        
    if not SAMSUNG_PAT:
        print("Error: SAMSUNG_PAT environment variable not set")
        return
    
    print("Starting Samsung SmartThings MCP Server...", file=sys.stderr)
    print(f"Available tools: get_devices, get_device_logs", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        try:
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
        finally:
            await cleanup()


if __name__ == "__main__":
    import sys
    asyncio.run(main())
