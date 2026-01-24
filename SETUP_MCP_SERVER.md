# Running Samsung SmartThings MCP Server

## Quick Start Guide

### Step 1: Verify MCP Server File

Make sure you have `samsung_smartthings_mcp.py` in your directory:
```
c:\Code\agentframework\msagentframework\samsung_smartthings_mcp.py
```

### Step 2: Test the MCP Server Locally (Optional)

Test if the server works:
```bash
python samsung_smartthings_mcp.py
```

If it starts without errors, press Ctrl+C to stop it.

### Step 3: Configure in Azure AI Foundry

1. **Open Azure AI Foundry Portal**
   - Go to https://ai.azure.com
   - Navigate to your project

2. **Find Your Agent**
   - Go to "Agents" section
   - Find `smartthingsagent`
   - Click "Edit"

3. **Add MCP Server**
   - Look for "MCP Servers" or "Tools" section
   - Click "Add MCP Server"
   - Fill in:
     - **Name**: `samsung-smartthings`
     - **Type**: `Local/STDIO`
     - **Command**: `python`
     - **Arguments**: `samsung_smartthings_mcp.py`
     - **Working Directory**: `c:\Code\agentframework\msagentframework`
     - **Environment Variables**: 
       - Key: `SAMSUNG_PAT`
       - Value: Your Samsung Personal Access Token

4. **Save the Agent**

### Step 4: Update Agent Instructions (Optional but Recommended)

Add this to your agent's instructions:
```
You have access to SmartThings devices through two MCP tools:
- get_devices: Lists all SmartThings devices
- get_device_logs: Gets detailed status for a specific device (requires device_id)

When users ask about their devices, use these tools to provide accurate information.
```

### Step 5: Test in Streamlit App

Run the streamlit app:
```bash
streamlit run stsmartthings.py
```

Try asking: "What SmartThings devices do I have?"

## Verification

If configured correctly, you should see in the debug console:
- 📊 Trace ID
- ℹ️ agent_info
- ⚠️ MCP Approval Request (if approval is required)
- ✔️ MCP Approved
- 🔧 MCP Tool Result

## Troubleshooting

### MCP Server Not Found
- Verify the working directory path is correct
- Make sure Python is in your PATH
- Try using absolute path: `C:\Python\python.exe`

### Authentication Errors
- Check `SAMSUNG_PAT` environment variable is set
- Verify token is valid at https://account.smartthings.com/tokens
- Ensure token has `r:devices:*` scope

### No Tool Calls Happening
- Check agent instructions mention the tools
- Verify MCP server is properly configured
- Look for errors in Azure AI Foundry agent logs

## Alternative: Using Agent Framework Config File

If you prefer configuration file approach, create `agent_config.json`:

```json
{
  "name": "smartthingsagent",
  "mcp_servers": {
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

## What Happens When It Works

1. You ask a question in Streamlit
2. Agent determines it needs device info
3. Agent calls MCP tool (get_devices or get_device_logs)
4. MCP server executes the Python function
5. Results are returned to agent
6. Agent formulates response with the data
7. You see the response in chat + debug logs show tool execution

## Current Status

Your Streamlit app is already configured to:
- ✅ Handle MCP approval requests automatically
- ✅ Show tool execution in debug console
- ✅ Display results in chat

You just need to configure the MCP server in Azure AI Foundry!
