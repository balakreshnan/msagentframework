import asyncio
import datetime
import os
from random import randint
from typing import Annotated
import re
import aiohttp
import pysmartthings
import json
import streamlit as st

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

# ============================================
# Streamlit Page Configuration
# ============================================
st.set_page_config(
    page_title="🏠 SmartThings AI Assistant",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for beautiful UI
st.markdown("""
<style>
    /* Main container styling */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    
    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    
    .main-header h1 {
        color: white;
        margin: 0;
        font-size: 1.8rem;
        font-weight: 600;
    }
    
    .main-header p {
        color: rgba(255,255,255,0.85);
        margin: 0.5rem 0 0 0;
        font-size: 0.95rem;
    }
    
    /* Column headers */
    .column-header {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
        padding: 0.8rem 1rem;
        border-radius: 8px 8px 0 0;
        border-bottom: 2px solid #667eea;
        margin-bottom: 0;
    }
    
    .column-header h3 {
        margin: 0;
        color: #2d3748;
        font-size: 1rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Chat message styling */
    .user-message {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.8rem 1rem;
        border-radius: 12px 12px 4px 12px;
        margin: 0.5rem 0;
        max-width: 85%;
        margin-left: auto;
        box-shadow: 0 2px 8px rgba(102, 126, 234, 0.25);
    }
    
    .assistant-message {
        background: #f8f9fa;
        color: #2d3748;
        padding: 0.8rem 1rem;
        border-radius: 12px 12px 12px 4px;
        margin: 0.5rem 0;
        max-width: 85%;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }
    
    /* Agent log styling */
    .agent-log-entry {
        background: #1a1a2e;
        color: #00ff88;
        padding: 0.6rem 0.8rem;
        border-radius: 6px;
        margin: 0.4rem 0;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 0.82rem;
        border-left: 3px solid #00ff88;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    
    .agent-log-entry.tool-call {
        color: #ffd700;
        border-left-color: #ffd700;
        background: #1a1a2e;
    }
    
    .agent-log-entry.info {
        color: #00bfff;
        border-left-color: #00bfff;
        background: #1a1a2e;
    }
    
    .agent-log-entry.success {
        color: #00ff88;
        border-left-color: #00ff88;
        background: #1a1a2e;
    }
    
    .agent-log-entry.error {
        color: #ff6b6b;
        border-left-color: #ff6b6b;
        background: #2a1a1a;
    }
    
    .agent-log-entry.output {
        color: #e0e0e0;
        border-left-color: #9b59b6;
        background: #1e1e2e;
    }
    
    /* Output content box */
    .agent-output-box {
        background: #0d0d1a;
        color: #e0e0e0;
        padding: 0.5rem 0.8rem;
        border-radius: 4px;
        margin-top: 0.3rem;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 0.75rem;
        max-height: 200px;
        overflow-y: auto;
        white-space: pre-wrap;
        word-break: break-word;
        border: 1px solid #333;
    }
    
    /* Timestamp styling */
    .timestamp {
        font-size: 0.7rem;
        color: #718096;
        margin-top: 0.3rem;
    }
    
    /* Status indicator */
    .status-indicator {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 500;
    }
    
    .status-online {
        background: #c6f6d5;
        color: #22543d;
    }
    
    .status-processing {
        background: #fef3c7;
        color: #92400e;
    }
    
    /* Container styling */
    .stContainer {
        border: 1px solid #e2e8f0;
        border-radius: 0 0 8px 8px;
    }
    
    /* Input styling */
    .stChatInput {
        border-radius: 25px !important;
    }
    
    /* Divider */
    .custom-divider {
        height: 2px;
        background: linear-gradient(90deg, transparent, #667eea, transparent);
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "agent_logs" not in st.session_state:
    st.session_state.agent_logs = []

if "processing" not in st.session_state:
    st.session_state.processing = False

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

async def main(query: str, log_callback=None) -> str:
    """
    This method creates a new agent version on the Azure AI service and returns
    a ChatAgent. Use this when you want to create a fresh agent with
    specific configuration.
    """
    logs = []
    
    def add_log(message: str, log_type: str = "info", output: str = None):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        log_entry = {"time": timestamp, "message": message, "type": log_type, "output": output}
        logs.append(log_entry)
        if log_callback:
            log_callback(log_entry)
    
    add_log("🚀 Initializing Azure AI Agent Provider...", "info")

    try:
        # First test if get_devices works directly
        add_log("🧪 Testing get_devices tool directly...", "info")
        try:
            test_devices = await get_devices()
            add_log(f"✅ Direct tool test: Found {len(test_devices)} devices", "success", 
                    output=json.dumps(test_devices, indent=2, default=str))
        except Exception as test_err:
            add_log(f"❌ Direct tool test failed: {str(test_err)}", "error")
        
        async with (
            DefaultAzureCredential() as credential,
            AzureAIProjectAgentProvider(credential=credential) as provider,
        ):
            add_log("✅ Azure credentials authenticated", "success")
            
            # Create a new agent with custom configuration
            add_log("🤖 Creating SmartThings Agent...", "info")
            
            agent = await provider.create_agent(
                name="SmartthingsAgent",
                instructions="""You are a helpful Samsung SmartThings AI Agent. 
                Always be concise. When listing devices, show device_id, label/name clearly.
                Use the get_devices tool to retrieve the list of devices.
                Use the get_device_logs tool with a device_id to get detailed status.""",
                description="An agent that provides information about home IoT devices.",
                tools=[get_devices, get_device_logs],
            )

            add_log(f"✅ Agent created: {agent.name}", "success", output=f"Agent ID: {agent.id}")
            add_log(f"📝 User Query: {query}", "info")
            
            add_log("🔄 Executing Agent...", "tool-call")
            
            # Use agent.run() to get the response
            result = await agent.run(query)
            print(f"Agent: {result}\n")
            
            # Log the raw result for debugging
            add_log(f"📊 Raw result type: {type(result).__name__}", "info", output=repr(result)[:500])
            
            # Convert result to string properly
            if hasattr(result, 'content'):
                full_response = str(result.content)
            elif hasattr(result, 'text'):
                full_response = str(result.text)
            elif hasattr(result, 'value'):
                full_response = str(result.value)
            else:
                full_response = str(result)
            
            add_log("✅ Agent Final Response:", "success", output=full_response)
            
            return full_response, logs
            
    except Exception as e:
        error_msg = str(e)
        add_log(f"❌ Error: {error_msg}", "error")
        import traceback
        tb = traceback.format_exc()
        add_log("📋 Traceback:", "error", output=tb)
        return f"Error occurred: {error_msg}", logs


# ============================================
# Streamlit UI Components
# ============================================
def render_header():
    """Render the main header"""
    st.markdown("""
        <div class="main-header">
            <h1>🏠 SmartThings AI Assistant</h1>
            <p>Control and monitor your Samsung SmartThings devices with natural language</p>
        </div>
    """, unsafe_allow_html=True)


def render_chat_message(role: str, content: str, timestamp: str):
    """Render a chat message with proper styling"""
    # Escape HTML and convert newlines to <br>
    safe_content = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
    
    if role == "user":
        st.markdown(f"""
            <div class="user-message">
                <strong>👤 You</strong><br>
                {safe_content}
                <div class="timestamp">{timestamp}</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div class="assistant-message">
                <strong>🤖 Assistant</strong><br>
                {safe_content}
                <div class="timestamp">{timestamp}</div>
            </div>
        """, unsafe_allow_html=True)


def render_agent_log(log_entry: dict):
    """Render an agent log entry with output"""
    log_type = log_entry.get("type", "info")
    message = log_entry.get("message", "")
    output = log_entry.get("output", None)
    
    # Escape HTML in output to prevent rendering issues
    if output:
        output = output.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    if output:
        st.markdown(f"""
            <div class="agent-log-entry {log_type}">
                <span style="opacity: 0.7">[{log_entry['time']}]</span> {message}
                <div class="agent-output-box">{output}</div>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
            <div class="agent-log-entry {log_type}">
                <span style="opacity: 0.7">[{log_entry['time']}]</span> {message}
            </div>
        """, unsafe_allow_html=True)


def main_ui():
    """Main Streamlit UI"""
    render_header()
    
    # Status indicator
    col_status, col_clear = st.columns([4, 1])
    with col_status:
        if st.session_state.processing:
            st.markdown('<span class="status-indicator status-processing">⏳ Processing...</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="status-indicator status-online">🟢 Ready</span>', unsafe_allow_html=True)
    
    with col_clear:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.agent_logs = []
            st.rerun()
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Two columns layout with medium gap
    left_col, spacer, right_col = st.columns([5, 0.5, 5])
    
    with left_col:
        st.markdown("""
            <div class="column-header">
                <h3>💬 Chat History</h3>
            </div>
        """, unsafe_allow_html=True)
        
        chat_container = st.container(height=500)
        with chat_container:
            if not st.session_state.chat_history:
                st.markdown("""
                    <div style="text-align: center; padding: 2rem; color: #718096;">
                        <p style="font-size: 3rem; margin-bottom: 1rem;">💬</p>
                        <p>No messages yet. Start a conversation!</p>
                        <p style="font-size: 0.85rem; margin-top: 1rem;">
                            Try asking:<br>
                            • "View all my devices"<br>
                            • "What's the status of my living room light?"<br>
                            • "Show me device logs"
                        </p>
                    </div>
                """, unsafe_allow_html=True)
            else:
                for msg in st.session_state.chat_history:
                    render_chat_message(msg["role"], msg["content"], msg["timestamp"])
    
    with right_col:
        st.markdown("""
            <div class="column-header">
                <h3>🤖 Agent Output & Logs</h3>
            </div>
        """, unsafe_allow_html=True)
        
        log_container = st.container(height=500)
        with log_container:
            if not st.session_state.agent_logs:
                st.markdown("""
                    <div style="text-align: center; padding: 2rem; color: #718096;">
                        <p style="font-size: 3rem; margin-bottom: 1rem;">🤖</p>
                        <p>Agent outputs will appear here</p>
                        <p style="font-size: 0.85rem; margin-top: 1rem;">
                            View real-time agent activity:<br>
                            • Tool calls & arguments<br>
                            • Raw tool outputs (JSON)<br>
                            • Agent responses
                        </p>
                    </div>
                """, unsafe_allow_html=True)
            else:
                for log in st.session_state.agent_logs:
                    render_agent_log(log)
    
    st.markdown('<div class="custom-divider"></div>', unsafe_allow_html=True)
    
    # Chat input at the bottom
    user_input = st.chat_input("Ask about your SmartThings devices...", key="chat_input")
    
    if user_input:
        st.session_state.processing = True
        timestamp = datetime.datetime.now().strftime("%I:%M %p")
        
        # Add user message to history
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "timestamp": timestamp
        })
        
        # Clear previous logs for new query
        st.session_state.agent_logs = []
        
        # Add initial log entry
        st.session_state.agent_logs.append({
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "message": f"📨 New query received: {user_input[:50]}...",
            "type": "info"
        })
        
        try:
            # Run the agent
            result, logs = asyncio.run(main(user_input))
            
            # Add all logs from agent execution
            st.session_state.agent_logs.extend(logs)
            
            # Add assistant response to chat history
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": result,
                "timestamp": datetime.datetime.now().strftime("%I:%M %p")
            })
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            st.session_state.agent_logs.append({
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
                "message": f"❌ {error_msg}",
                "type": "error"
            })
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"Sorry, I encountered an error: {error_msg}",
                "timestamp": datetime.datetime.now().strftime("%I:%M %p")
            })
        
        st.session_state.processing = False
        st.rerun()


if __name__ == "__main__":
    main_ui()