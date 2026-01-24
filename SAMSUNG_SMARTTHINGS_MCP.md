# Samsung SmartThings MCP Server

Local MCP (Model Context Protocol) server for interacting with Samsung SmartThings devices.

## Files

- `samsung_smartthings_mcp.py` - MCP server with SmartThings tools
- `stsmartthings_agent.py` - Example agent using the MCP server
- `stsamdevices.py` - Simple script to list devices (standalone)

## Setup

### 1. Install Dependencies

```bash
pip install pysmartthings mcp aiohttp python-dotenv
```

### 2. Get Samsung Personal Access Token

1. Go to https://account.smartthings.com/tokens
2. Create a new token with these scopes:
   - `r:devices:*` (read devices)
   - `r:locations:*` (read locations) - optional

3. Add to `.env` file:
```
SAMSUNG_PAT=your-token-here
```

## MCP Server Tools

### Tool 1: `get_devices`

Get all Samsung SmartThings devices with their components and capabilities.

**Parameters:** None

**Returns:**
```json
{
  "success": true,
  "device_count": 5,
  "devices": [
    {
      "device_id": "abc123",
      "label": "Living Room Light",
      "name": "GE Smart Switch",
      "type": "SWITCH",
      "components": {
        "main": {
          "capabilities": ["switch", "switchLevel", "powerMeter"]
        }
      }
    }
  ]
}
```

### Tool 2: `get_device_logs`

Get detailed status, events, and logs for a specific device.

**Parameters:**
- `device_id` (string, required) - The device ID

**Returns:**
```json
{
  "success": true,
  "device": {
    "device_id": "abc123",
    "label": "Living Room Light",
    "components": {
      "main": {
        "capabilities": ["switch", "switchLevel"],
        "attributes": {
          "switch": {"value": "on"},
          "switchLevel": {"value": "75"}
        }
      }
    },
    "health": {
      "state": "ONLINE",
      "last_updated": "2026-01-24T10:30:00Z"
    }
  }
}
```

## Usage

### Option 1: Run MCP Server Standalone

Start the MCP server:
```bash
python samsung_smartthings_mcp.py
```

The server will run in stdio mode and can be connected to by MCP clients.

### Option 2: Use with Agent Framework

Run the example agent:
```bash
python stsmartthings_agent.py
```

This will:
1. Connect to the MCP server
2. Create an AI agent with SmartThings capabilities
3. Run example queries to list devices

### Option 3: Integrate into Your Own Agent

```python
from agent_framework import HostedMCPTool

# Create MCP tool
smartthings_mcp = HostedMCPTool(
    name="Samsung SmartThings",
    url="stdio://samsung_smartthings_mcp.py",
    approval_mode='never_require'
)

# Add to your agent
agent = chat_client.create_agent(
    name="Your Agent",
    instructions="Your instructions...",
    tools=[smartthings_mcp],
    model="gpt-4o"
)
```

## Simple Device Listing (No MCP)

For a quick device listing without the MCP server:
```bash
python stsamdevices.py
```

## Troubleshooting

### "Forbidden" Error
- Check your `SAMSUNG_PAT` token is valid
- Verify the token has required scopes (`r:devices:*`)
- Token may have expired - create a new one

### "AttributeError" Errors
- Make sure you're using the latest `pysmartthings` library
- Check that method names match the library version

### No Devices Returned
- Verify you have devices in your SmartThings account
- Check that devices are online in the SmartThings app
- Ensure your token has permission to access devices

## Examples

### List All Devices
```python
# The agent will call get_devices tool
"What SmartThings devices do I have?"
```

### Get Device Details
```python
# First get device ID, then:
"Show me detailed information about device abc123"
```

### Check Device Status
```python
"What's the current status of my living room light?"
```

## API Reference

The MCP server uses the `pysmartthings` library:
- [pysmartthings Documentation](https://github.com/andrewsayre/pysmartthings)
- [SmartThings API Documentation](https://developer.smartthings.com/docs/api/public)
