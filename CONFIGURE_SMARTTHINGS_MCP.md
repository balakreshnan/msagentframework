# Adding SmartThings MCP Tools to Existing Agent

This guide shows how to add the SmartThings MCP server to your existing `smartthingsagent` in Azure AI Foundry.

## Setup Steps

### 1. Ensure MCP Library is Installed

```bash
pip install mcp
```

### 2. Test the MCP Server Locally

```bash
python samsung_smartthings_mcp.py
```

The server should start and wait for input. Press Ctrl+C to stop.

### 3. Add MCP Server to Azure AI Foundry Agent

#### Option A: Using Azure AI Foundry Portal

1. Go to Azure AI Foundry portal
2. Navigate to your project
3. Find your existing agent: `smartthingsagent`
4. Click "Edit Agent"
5. Go to "MCP Servers" or "Tools" section
6. Add a new MCP server with these settings:
   - **Name**: `samsung-smartthings`
   - **Command**: `python`
   - **Args**: `samsung_smartthings_mcp.py`
   - **Working Directory**: `c:\Code\agentframework\msagentframework`
   - **Environment Variables**: 
     - `SAMSUNG_PAT`: Your Samsung Personal Access Token

#### Option B: Using Agent Configuration File

If your agent is defined in a configuration file, add this to the MCP servers section:

```json
{
  "mcpServers": {
    "samsung-smartthings": {
      "command": "python",
      "args": ["samsung_smartthings_mcp.py"],
      "cwd": "c:\\Code\\agentframework\\msagentframework",
      "env": {
        "SAMSUNG_PAT": "${env:SAMSUNG_PAT}"
      }
    }
  }
}
```

#### Option C: Programmatically with Agent Framework

Update your `agent_main` function to include the MCP tool:

```python
def agent_main(query: str):
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )
    
    # Create MCP tool reference
    smartthings_mcp = HostedMCPTool(
        name="samsung-smartthings",
        url="stdio://samsung_smartthings_mcp.py",
        approval_mode='never_require'
    )
    
    myAgent = "smartthingsagent"
    
    # Get existing agent and update with MCP tool
    agent = project_client.agents.get(agent_name=myAgent)
    
    # Add MCP server to agent (if not already configured)
    # This depends on your specific agent framework version
    
    # Continue with rest of agent_main...
```

### 4. Update Agent Instructions

Make sure your `smartthingsagent` instructions include information about the available tools:

```
You are a Samsung SmartThings home automation assistant.

Available MCP Tools:
- get_devices: Get all Samsung SmartThings devices with their components and capabilities
- get_device_logs: Get detailed status, events, and logs for a specific device (requires device_id)

When asked about devices:
1. Use get_devices to list all available devices
2. Use get_device_logs with a device_id to get detailed information
3. Present information clearly and explain capabilities in plain language
```

## Available MCP Tools

### `get_devices`
Returns all SmartThings devices with their components and capabilities.

**Parameters:** None

**Example Response:**
```json
{
  "success": true,
  "device_count": 3,
  "devices": [
    {
      "device_id": "abc123",
      "label": "Living Room Light",
      "name": "GE Smart Switch",
      "type": "SWITCH",
      "components": {
        "main": {
          "capabilities": ["switch", "switchLevel"]
        }
      }
    }
  ]
}
```

### `get_device_logs`
Gets detailed status and logs for a specific device.

**Parameters:**
- `device_id` (string, required): The device ID to query

**Example Request:**
```json
{
  "device_id": "abc123"
}
```

**Example Response:**
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
  },
  "timestamp": "2026-01-24T10:35:00"
}
```

## Testing with Existing Agent

Once configured, you can test with your existing `agent_main` function:

```python
# Run the existing agent with SmartThings queries
agent_main("What SmartThings devices do I have?")
agent_main("Show me the status of device abc123")
```

The agent will automatically discover and use the MCP tools when needed.

## Troubleshooting

### MCP Server Not Found
- Verify the path in `cwd` is correct
- Make sure `samsung_smartthings_mcp.py` exists in that directory
- Check that Python is in your PATH

### Authentication Errors
- Verify `SAMSUNG_PAT` environment variable is set
- Check that the token is valid and has required scopes (`r:devices:*`)
- Token may have expired - create a new one at https://account.smartthings.com/tokens

### MCP Approval Requests
If you see MCP approval requests in the output, they should be auto-approved by the existing code in `agent_main`. If not, check that the approval logic is present.

## File Structure

```
msagentframework/
├── samsung_smartthings_mcp.py          # MCP server
├── smartthings_mcp_config.json         # Configuration file
├── stsamdevices.py                      # Your existing agent code
└── .env                                 # Environment variables (SAMSUNG_PAT)
```
