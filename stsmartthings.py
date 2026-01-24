import asyncio
import re
import aiohttp
import pysmartthings
import os
import json
from datetime import datetime
from typing import Dict, List, Any
import streamlit as st
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework import observability
import time
import subprocess
import sys

# Load environment variables
load_dotenv()

TOKEN = os.getenv("SAMSUNG_PAT")
myEndpoint = os.getenv("AZURE_AI_PROJECT")

# Page config
st.set_page_config(
    page_title="SmartThings Agent",
    page_icon="🏠",
    layout="wide"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .stApp {
        max-width: 100%;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        background-color: #f0f2f6;
    }
    .user-message {
        background-color: #e3f2fd;
        border-left: 4px solid #2196f3;
    }
    .assistant-message {
        background-color: #f1f8e9;
        border-left: 4px solid #4caf50;
    }
    .debug-item {
        padding: 0.5rem;
        margin: 0.5rem 0;
        border-radius: 0.3rem;
        background-color: #263238;
        color: #aed581;
        font-family: monospace;
        font-size: 0.85rem;
    }
    .tool-call {
        background-color: #1a237e;
        color: #64b5f6;
    }
    .stButton button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

if 'debug_logs' not in st.session_state:
    st.session_state.debug_logs = []

if 'agent_ready' not in st.session_state:
    st.session_state.agent_ready = True

if 'available_tools' not in st.session_state:
    st.session_state.available_tools = []

if 'mcp_server_status' not in st.session_state:
    st.session_state.mcp_server_status = "Not Started"


def get_local_tools():
    """Get available tools from local functions"""
    return [
        {
            "name": "get_smartthings_devices",
            "description": "Get all Samsung SmartThings devices with their components and capabilities",
            "parameters": {}
        },
        {
            "name": "get_smartthings_device_logs",
            "description": "Get detailed status, events, and logs for a specific Samsung SmartThings device",
            "parameters": {
                "device_id": "string (required) - The device ID to get logs for"
            }
        }
    ]


def call_local_tool(tool_name: str, **kwargs):
    """Call a local tool function directly"""
    if tool_name == "get_smartthings_devices":
        return asyncio.run(getdevices())
    elif tool_name == "get_smartthings_device_logs":
        device_id = kwargs.get("device_id")
        if device_id:
            return asyncio.run(get_device_logs(device_id))
        else:
            return {"error": "device_id is required"}
    else:
        return {"error": f"Unknown tool: {tool_name}"}


async def getdevices():
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
        
        await device.status.refresh()
        
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


def run_agent(query: str):
    """Run the SmartThings agent with a query"""
    debug_logs = []
    response_text = ""
    
  
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )
    
    myAgent = "smartthingsagent"
    
    with observability.get_tracer().start_as_current_span("smartthingsagent", kind=SpanKind.CLIENT) as current_span:
        trace_id = format_trace_id(current_span.get_span_context().trace_id)
        debug_logs.append({
            "type": "trace",
            "trace_id": trace_id,
            "timestamp": datetime.now().isoformat()
        })
        
        # Get agent
        agent = project_client.agents.get(agent_name=myAgent)
        debug_logs.append({
            "type": "agent_info",
            "agent_name": agent.name,
            "timestamp": datetime.now().isoformat()
        })
        
        openai_client = project_client.get_openai_client()
        
      
        # Create response (tools are configured on the agent in Azure AI Foundry, not passed here)
        response = openai_client.responses.create(
            input=[{"role": "user", "content": query}],
            extra_body={"agent": {"name": agent.name, "type": "agent_reference"}}
        )
        
        debug_logs.append({
            "type": "response_created",
            "response_id": response.id,
            "status": response.status,
            "output_count": len(response.output) if hasattr(response, 'output') else 0,
            "timestamp": datetime.now().isoformat()
        })
        
        # Log all output items for visibility
        for idx, output_item in enumerate(response.output):
            debug_logs.append({
                "type": "output_item",
                "index": idx,
                "item_type": getattr(output_item, 'type', 'unknown'),
                "item_data": str(output_item)[:500],
                "timestamp": datetime.now().isoformat()
            })
        
        # Check for MCP approval requests
        mcp_approval_requests = []
        tool_results = {}  # Store tool results by tool name
        
        for output_item in response.output:
            if hasattr(output_item, 'type') and output_item.type == 'mcp_approval_request':
                mcp_approval_requests.append(output_item)
                debug_logs.append({
                    "type": "mcp_approval_request",
                    "tool": output_item.name,
                    "arguments": output_item.arguments,
                    "full_request": str(output_item)[:500],
                    "timestamp": datetime.now().isoformat()
                })
                
                # Check if this is a local tool we can execute
                tool_name = output_item.name
                if tool_name in tools:
                    try:
                        debug_logs.append({
                            "type": "local_tool_execution",
                            "tool": tool_name,
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        # Parse arguments
                        args = {}
                        if hasattr(output_item, 'arguments') and output_item.arguments:
                            try:
                                args = json.loads(output_item.arguments) if isinstance(output_item.arguments, str) else output_item.arguments
                            except:
                                pass
                        
                        # Execute the local function
                        tool_func = tools[tool_name]
                        if args:
                            result = tool_func(**args)
                        else:
                            result = tool_func()
                        
                        # Store result by tool name
                        tool_results[tool_name] = result
                        
                        debug_logs.append({
                            "type": "local_tool_completed",
                            "tool": tool_name,
                            "result_preview": str(result)[:200],
                            "full_result": result,
                            "timestamp": datetime.now().isoformat()
                        })
                        
                    except Exception as e:
                        debug_logs.append({
                            "type": "local_tool_error",
                            "tool": tool_name,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
        
        # Auto-approve MCP calls (even though we already executed them locally)
        if mcp_approval_requests:
            debug_logs.append({
                "type": "info",
                "message": f"Processing {len(mcp_approval_requests)} local tool call(s)",
                "timestamp": datetime.now().isoformat()
            })
            
            # Note: We already executed the tools above, but we still approve for the agent flow
            # In a real scenario with MCP server, the approval would trigger server-side execution
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
                debug_logs.append({
                    "type": "mcp_approved",
                    "tool": approval_request.name,
                    "timestamp": datetime.now().isoformat()
                })
            
            # Poll for completion
            max_retries = 30
            retry_count = 0
            
            while retry_count < max_retries:
                response = openai_client.responses.retrieve(response_id=response.id)
                
                if response.status == 'completed':
                    debug_logs.append({
                        "type": "response_completed",
                        "timestamp": datetime.now().isoformat()
                    })
                    break
                elif response.status == 'failed':
                    debug_logs.append({
                        "type": "response_failed",
                        "error": str(response.error) if response.error else "Unknown error",
                        "timestamp": datetime.now().isoformat()
                    })
                    break
                else:
                    time.sleep(2)
                    retry_count += 1
            
            # After completion, inject local tool results into response if MCP server didn't provide them
            debug_logs.append({
                "type": "info",
                "message": f"Injecting {len(tool_results)} local tool results into response",
                "timestamp": datetime.now().isoformat()
            })
            
            for tool_name, result in tool_results.items():
                response_text += f"\n\n[Local Tool Result - {tool_name}]:\n{result}\n\n"
        
        # Extract response text and handle local function calls
        debug_logs.append({
            "type": "extracting_response",
            "total_outputs": len(response.output),
            "timestamp": datetime.now().isoformat()
        })
        
        for idx, output_item in enumerate(response.output):
            item_type = getattr(output_item, 'type', None)
            
            debug_logs.append({
                "type": "processing_output",
                "index": idx,
                "item_type": item_type,
                "timestamp": datetime.now().isoformat()
            })
            
            if item_type == 'message':
                if hasattr(output_item, 'content') and output_item.content:
                    for content_item in output_item.content:
                        if hasattr(content_item, 'text'):
                            text_content = content_item.text
                            response_text += text_content + "\n"
                            debug_logs.append({
                                "type": "message_content",
                                "content": text_content,
                                "timestamp": datetime.now().isoformat()
                            })
            
            elif item_type == 'response_output_text':
                text_content = output_item.text
                response_text += text_content + "\n"
                debug_logs.append({
                    "type": "response_text",
                    "content": text_content,
                    "timestamp": datetime.now().isoformat()
                })
            
            elif item_type == 'mcp_call':
                # Check if this is a local tool we can execute
                tool_name = output_item.name
                if tool_name in tools:
                    try:
                        debug_logs.append({
                            "type": "local_tool_execution",
                            "tool": tool_name,
                            "timestamp": datetime.now().isoformat()
                        })
                        
                        # Execute the local function
                        tool_func = tools[tool_name]
                        # Parse arguments if available
                        args = {}
                        if hasattr(output_item, 'arguments') and output_item.arguments:
                            try:
                                args = json.loads(output_item.arguments) if isinstance(output_item.arguments, str) else output_item.arguments
                            except:
                                pass
                        
                        # Call the function
                        if args:
                            result = tool_func(**args)
                        else:
                            result = tool_func()
                        
                        debug_logs.append({
                            "type": "local_tool_completed",
                            "tool": tool_name,
                            "timestamp": datetime.now().isoformat()
                        })
                    except Exception as e:
                        debug_logs.append({
                            "type": "local_tool_error",
                            "tool": tool_name,
                            "error": str(e),
                            "timestamp": datetime.now().isoformat()
                        })
                
                debug_logs.append({
                    "type": "mcp_call_result",
                    "tool": output_item.name,
                    "status": output_item.status,
                    "timestamp": datetime.now().isoformat()
                })
        
        debug_logs.append({
            "type": "final_response",
            "response_length": len(response_text),
            "response_preview": response_text[:500] if response_text else "No response text",
            "timestamp": datetime.now().isoformat()
        })
    
    return response_text.strip(), debug_logs


# App Header
st.title("🏠 SmartThings Agent")
st.markdown("Chat with your SmartThings home automation assistant")

# Create two columns
col1, col2 = st.columns(2, gap="medium")

# Left Column - Chat History
with col1:
    st.subheader("💬 Chat")
    
    chat_container = st.container(height=500)
    
    with chat_container:
        for msg in st.session_state.chat_history:
            if msg["role"] == "user":
                st.markdown(f"""
                <div class="chat-message user-message">
                    <strong>You:</strong><br>
                    {msg["content"]}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="chat-message assistant-message">
                    <strong>Assistant:</strong><br>
                    {msg["content"]}
                </div>
                """, unsafe_allow_html=True)

# Right Column - Debug Info
with col2:
    st.subheader("🔍 Debug Console")
    
    debug_container = st.container(height=500)
    
    with debug_container:
        if st.session_state.debug_logs:
            for idx, log in enumerate(st.session_state.debug_logs):
                log_type = log.get("type", "unknown")
                timestamp = log.get('timestamp', '')
                
                if log_type == "tool_call":
                    with st.expander(f"🔧 Tool Call: {log.get('tool', 'unknown')} - {timestamp}", expanded=False):
                        st.json(log)
                
                elif log_type == "tool_result":
                    with st.expander(f"✅ Tool Result: {log.get('tool', 'unknown')} - {timestamp}", expanded=False):
                        st.json(log)
                
                elif log_type == "trace":
                    with st.expander(f"📊 Trace: {log.get('trace_id', 'N/A')[:8]}... - {timestamp}", expanded=False):
                        st.json(log)
                
                elif log_type == "mcp_approval_request":
                    with st.expander(f"⚠️ MCP Approval: {log.get('tool', 'unknown')} - {timestamp}", expanded=True):
                        st.markdown(f"**Tool:** {log.get('tool', 'unknown')}")
                        if log.get('arguments'):
                            st.markdown("**Arguments:**")
                            st.json(log.get('arguments'))
                        if log.get('full_request'):
                            st.markdown("**Full Request:**")
                            st.code(log.get('full_request'), language="text")
                        st.json(log)
                
                elif log_type == "error":
                    error_detail = log.get('error', 'Unknown error')
                    traceback_info = log.get('traceback', '')
                    with st.expander(f"❌ Error: {log.get('error_type', 'Error')} - {timestamp}", expanded=True):
                        st.error(f"**{log.get('error_type', 'Error')}:** {error_detail}")
                        if traceback_info:
                            st.code(traceback_info, language="python")
                        st.json(log)
                
                elif log_type == "local_tool_execution":
                    with st.expander(f"⚡ Executing: {log.get('tool', 'unknown')} - {timestamp}", expanded=True):
                        st.markdown(f"**Local Tool:** {log.get('tool', 'unknown')}")
                        st.json(log)
                
                elif log_type == "local_tool_completed":
                    with st.expander(f"✅ Completed: {log.get('tool', 'unknown')} - {timestamp}", expanded=True):
                        st.success(f"Tool **{log.get('tool', 'unknown')}** completed successfully")
                        if log.get('result_preview'):
                            st.markdown("**Result Preview:**")
                            st.code(log.get('result_preview'), language="json")
                        if log.get('full_result'):
                            st.markdown("**Full Result:**")
                            st.json(log.get('full_result'))
                        else:
                            st.json(log)
                
                elif log_type == "local_tool_error":
                    with st.expander(f"⚠️ Tool Error: {log.get('tool', 'unknown')} - {timestamp}", expanded=True):
                        st.error(f"**Error in {log.get('tool', 'unknown')}:**")
                        st.code(log.get('error', 'Unknown error'))
                        st.json(log)
                
                elif log_type == "mcp_call_result":
                    with st.expander(f"🔧 MCP Result: {log.get('tool', 'unknown')} - {timestamp}", expanded=False):
                        st.markdown(f"**Tool:** {log.get('tool', 'unknown')}")
                        st.markdown(f"**Status:** {log.get('status', 'N/A')}")
                        st.json(log)
                
                elif log_type == "response_created":
                    with st.expander(f"📨 Response Created - {timestamp}", expanded=False):
                        st.markdown(f"**Response ID:** {log.get('response_id', 'N/A')}")
                        st.markdown(f"**Status:** {log.get('status', 'N/A')}")
                        st.markdown(f"**Output Count:** {log.get('output_count', 0)}")
                        st.json(log)
                
                elif log_type == "response_completed":
                    with st.expander(f"✅ Response Completed - {timestamp}", expanded=False):
                        st.success("Agent response completed successfully")
                        st.json(log)
                
                elif log_type == "response_failed":
                    with st.expander(f"❌ Response Failed - {timestamp}", expanded=True):
                        st.error(f"Error: {log.get('error', 'Unknown error')}")
                        st.json(log)
                
                elif log_type == "mcp_approved":
                    with st.expander(f"✔️ Approved: {log.get('tool', 'unknown')} - {timestamp}", expanded=False):
                        st.markdown(f"**Tool:** {log.get('tool', 'unknown')}")
                        st.json(log)
                
                elif log_type == "agent_info":
                    with st.expander(f"ℹ️ Agent Info - {timestamp}", expanded=False):
                        st.markdown(f"**Agent Name:** {log.get('agent_name', 'N/A')}")
                        if log.get('tools_count'):
                            st.markdown(f"**Tools Count:** {log.get('tools_count')}")
                        st.json(log)
                
                elif log_type == "output_item":
                    with st.expander(f"📦 Output Item #{log.get('index', 0)} ({log.get('item_type', 'unknown')}) - {timestamp}", expanded=False):
                        st.markdown(f"**Type:** {log.get('item_type', 'unknown')}")
                        st.markdown(f"**Index:** {log.get('index', 0)}")
                        if log.get('item_data'):
                            st.markdown("**Data:**")
                            st.code(log.get('item_data'), language="text")
                        st.json(log)
                
                elif log_type == "extracting_response":
                    with st.expander(f"🔍 Extracting Response - {timestamp}", expanded=False):
                        st.markdown(f"**Total Outputs:** {log.get('total_outputs', 0)}")
                        st.json(log)
                
                elif log_type == "processing_output":
                    with st.expander(f"⚙️ Processing Output #{log.get('index', 0)} - {timestamp}", expanded=False):
                        st.markdown(f"**Item Type:** {log.get('item_type', 'unknown')}")
                        st.json(log)
                
                elif log_type == "message_content":
                    with st.expander(f"💬 Agent Message - {timestamp}", expanded=True):
                        st.markdown("**Content:**")
                        st.markdown(log.get('content', ''))
                        st.json(log)
                
                elif log_type == "response_text":
                    with st.expander(f"📝 Response Text - {timestamp}", expanded=True):
                        st.markdown("**Content:**")
                        st.markdown(log.get('content', ''))
                        st.json(log)
                
                elif log_type == "final_response":
                    with st.expander(f"🎯 Final Response - {timestamp}", expanded=True):
                        st.markdown(f"**Response Length:** {log.get('response_length', 0)} characters")
                        st.markdown("**Response Preview:**")
                        st.code(log.get('response_preview', 'No response'), language="text")
                        st.json(log)
                
                elif log_type == "info":
                    with st.expander(f"ℹ️ Info - {timestamp}", expanded=False):
                        st.info(log.get('message', 'Info message'))
                        st.json(log)
                
                else:
                    with st.expander(f"ℹ️ {log_type} - {timestamp}", expanded=False):
                        st.json(log)
        else:
            st.info("Debug logs will appear here when you send a message")

# Chat Input
st.markdown("---")

# Example prompts
with st.expander("💡 Example Prompts"):
    if st.button("What SmartThings devices do I have?"):
        st.session_state.pending_query = "What SmartThings devices do I have?"
    if st.button("Show me the status of my devices"):
        st.session_state.pending_query = "Show me the status of my devices"
    if st.button("List all my smart lights"):
        st.session_state.pending_query = "List all my smart lights"

# Chat input
user_input = st.chat_input("Ask about your SmartThings devices...")

# Handle pending query from example buttons
if 'pending_query' in st.session_state:
    user_input = st.session_state.pending_query
    del st.session_state.pending_query

if user_input:
    # Add user message to history
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_input
    })
    
    # Clear previous debug logs for this interaction
    st.session_state.debug_logs = []
    
    # Show loading
    with st.spinner("🤔 Agent is thinking..."):
        try:
            # Run agent
            response, debug_logs = run_agent(user_input)
            
            # Add assistant response to history
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": response if response else "I couldn't generate a response. Please try again."
            })
            
            # Update debug logs
            st.session_state.debug_logs = debug_logs
            
        except Exception as e:
            import traceback
            error_msg = str(e)
            error_type = type(e).__name__
            error_traceback = traceback.format_exc()
            
            st.error(f"Error: {error_type} - {error_msg}")
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"Sorry, I encountered an error: {error_type} - {error_msg}"
            })
            # Add error to debug logs - ensure we don't try to serialize complex objects
            st.session_state.debug_logs.append({
                "type": "error",
                "error": error_msg,
                "error_type": error_type,
                "traceback": error_traceback[:500],  # Limit traceback length
                "timestamp": datetime.now().isoformat()
            })
    
    # Rerun to update the display
    st.rerun()

# Sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.chat_history = []
        st.session_state.debug_logs = []
        st.rerun()
    
    st.markdown("---")
    
    # Local Tools Section
    st.subheader("🔧 Available Local Tools")
    
    # Get and display available tools
    st.session_state.available_tools = get_local_tools()
    
    for tool in st.session_state.available_tools:
        with st.expander(f"📌 {tool['name']}"):
            st.markdown(f"**Description:** {tool['description']}")
            if tool['parameters']:
                st.markdown("**Parameters:**")
                for param, desc in tool['parameters'].items():
                    st.markdown(f"- `{param}`: {desc}")
            else:
                st.markdown("**Parameters:** None")
            
            # Add test button for each tool
            if tool['name'] == "get_smartthings_devices":
                if st.button(f"🧪 Test {tool['name']}", key=f"test_{tool['name']}"):
                    with st.spinner("Calling tool..."):
                        try:
                            result = call_local_tool(tool['name'])
                            st.success(f"Retrieved {len(result)} devices")
                            st.json(result)
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            
            elif tool['name'] == "get_smartthings_device_logs":
                device_id_input = st.text_input(
                    "Device ID:", 
                    key=f"device_id_{tool['name']}",
                    help="Enter a device ID from get_smartthings_devices"
                )
                if st.button(f"🧪 Test {tool['name']}", key=f"test_{tool['name']}"):
                    if device_id_input:
                        with st.spinner("Calling tool..."):
                            try:
                                result = call_local_tool(tool['name'], device_id=device_id_input)
                                st.success("Retrieved device logs")
                                st.json(result)
                            except Exception as e:
                                st.error(f"Error: {str(e)}")
                    else:
                        st.warning("Please enter a device ID")
    
    st.markdown("---")
    
    st.markdown("""
    ### About
    This SmartThings Agent helps you:
    - View all your devices
    - Check device status
    - Get detailed device logs
    - Control your smart home
    
    ### Status
    """)
    
    if st.session_state.agent_ready:
        st.success("✅ Agent Ready")
    else:
        st.error("❌ Agent Not Ready")
    
    st.markdown("**Local Tools:**")
    st.info(f"✅ {len(st.session_state.available_tools)} tools available")
    
    st.markdown(f"""
    **Messages:** {len(st.session_state.chat_history)}  
    **Debug Logs:** {len(st.session_state.debug_logs)}
    """)
