import asyncio
import logging
import streamlit as st
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ResponseStreamEventType
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
import os
from dotenv import load_dotenv
from datetime import datetime
import time
import base64

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

myEndpoint = os.getenv("AZURE_AI_PROJECT")

# ============================================================================
# MATERIAL DESIGN 3 STYLING
# ============================================================================
def apply_material_design_3():
    """Apply Material Design 3 inspired styling to Streamlit."""
    st.markdown("""
    <style>
        /* Material Design 3 Color Palette - Industrial Theme */
        :root {
            --md-sys-color-primary: #1565C0;
            --md-sys-color-on-primary: #FFFFFF;
            --md-sys-color-primary-container: #D1E4FF;
            --md-sys-color-on-primary-container: #001D36;
            --md-sys-color-secondary: #546E7A;
            --md-sys-color-on-secondary: #FFFFFF;
            --md-sys-color-secondary-container: #CFE6F1;
            --md-sys-color-surface: #F8FAFC;
            --md-sys-color-surface-variant: #E3E8ED;
            --md-sys-color-on-surface: #1A1C1E;
            --md-sys-color-on-surface-variant: #42474E;
            --md-sys-color-outline: #72787E;
            --md-sys-color-outline-variant: #C2C7CE;
            --md-sys-color-error: #BA1A1A;
            --md-sys-color-success: #2E7D32;
            --md-sys-color-warning: #F57C00;
        }
        
        /* Main app background */
        .stApp {
            background: linear-gradient(135deg, #F8FAFC 0%, #E3E8ED 100%);
        }
        
        /* Container styling */
        .chat-container {
            background-color: white;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.12);
            margin-bottom: 16px;
        }
        
        .output-container {
            background-color: white;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.12);
        }
        
        /* Message bubbles */
        .user-message {
            background-color: var(--md-sys-color-primary-container);
            color: var(--md-sys-color-on-primary-container);
            padding: 12px 16px;
            border-radius: 20px 20px 4px 20px;
            margin: 8px 0;
            max-width: 85%;
            margin-left: auto;
        }
        
        .assistant-message {
            background-color: var(--md-sys-color-surface-variant);
            color: var(--md-sys-color-on-surface);
            padding: 12px 16px;
            border-radius: 20px 20px 20px 4px;
            margin: 8px 0;
            max-width: 85%;
        }
        
        /* Debug message */
        .debug-message {
            background-color: #FFF8E1;
            border-left: 4px solid #FFA000;
            padding: 8px 12px;
            margin: 4px 0;
            border-radius: 0 8px 8px 0;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 12px;
        }
        
        /* Agent action message */
        .agent-action {
            background-color: #E3F2FD;
            border-left: 4px solid #1565C0;
            padding: 10px 14px;
            margin: 6px 0;
            border-radius: 0 12px 12px 0;
            font-family: 'Segoe UI', sans-serif;
        }
        
        /* Workflow step */
        .workflow-step {
            background-color: #F3E5F5;
            border-left: 4px solid #7B1FA2;
            padding: 8px 12px;
            margin: 4px 0;
            border-radius: 0 8px 8px 0;
        }
        
        /* Token usage badge */
        .token-badge {
            display: inline-block;
            background-color: var(--md-sys-color-secondary-container);
            color: var(--md-sys-color-secondary);
            padding: 4px 12px;
            border-radius: 16px;
            font-size: 12px;
            margin: 4px;
        }
        
        /* Header styling */
        .md-header {
            color: var(--md-sys-color-primary);
            font-weight: 600;
            font-size: 20px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        /* Subheader */
        .md-subheader {
            color: var(--md-sys-color-on-surface-variant);
            font-size: 14px;
            margin-bottom: 12px;
        }
        
        /* Status indicators */
        .status-processing {
            color: var(--md-sys-color-primary);
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .status-complete {
            color: var(--md-sys-color-success);
            font-weight: 500;
        }
        
        .status-error {
            color: var(--md-sys-color-error);
            font-weight: 500;
        }
        
        /* Timestamp */
        .timestamp {
            color: var(--md-sys-color-outline);
            font-size: 11px;
            margin-top: 4px;
        }
        
        /* Progress bar customization */
        .stProgress > div > div > div {
            background: linear-gradient(90deg, #1565C0, #42A5F5);
        }
        
        /* File uploader styling */
        .stFileUploader > div {
            border: 2px dashed var(--md-sys-color-outline-variant);
            border-radius: 12px;
        }
        
        /* Divider */
        .md-divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--md-sys-color-outline-variant), transparent);
            margin: 16px 0;
        }
        
        /* Chip/Tag */
        .md-chip {
            display: inline-block;
            background-color: var(--md-sys-color-surface-variant);
            color: var(--md-sys-color-on-surface-variant);
            padding: 6px 12px;
            border-radius: 8px;
            font-size: 12px;
            margin: 2px;
            font-weight: 500;
        }
        
        .md-chip-primary {
            background-color: var(--md-sys-color-primary-container);
            color: var(--md-sys-color-on-primary-container);
        }
        
        /* Plant IQ Branding */
        .plantiq-logo {
            font-size: 32px;
            font-weight: 700;
            background: linear-gradient(135deg, #1565C0 0%, #42A5F5 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .plantiq-subtitle {
            color: var(--md-sys-color-on-surface-variant);
            font-size: 14px;
            font-weight: 400;
        }
        
        /* Hide Streamlit branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        
        ::-webkit-scrollbar-track {
            background: var(--md-sys-color-surface-variant);
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--md-sys-color-outline);
            border-radius: 3px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--md-sys-color-on-surface-variant);
        }
        
        /* Card styling */
        .info-card {
            background: white;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            margin: 8px 0;
        }
    </style>
    """, unsafe_allow_html=True)

# ============================================================================
# TELEMETRY SETUP
# ============================================================================
def setup_telemetry():
    """Initialize telemetry for logging conversations to Foundry."""
    if st.session_state.get('telemetry_initialized', False):
        return True
    
    try:
        project_client = AIProjectClient(
            endpoint=myEndpoint,
            credential=DefaultAzureCredential(),
        )
        
        conn_string = project_client.telemetry.get_application_insights_connection_string()
        configure_azure_monitor(
            connection_string=conn_string,
            enable_live_metrics=True,
            resource=create_resource(),
            enable_performance_counters=False,
        )
        enable_instrumentation(enable_sensitive_data=True)
        st.session_state['telemetry_initialized'] = True
        logger.info("Telemetry initialized successfully for PlantIQ")
        return True
    except Exception as e:
        logger.warning(f"Could not initialize telemetry: {e}")
        return False

# ============================================================================
# ANALYZE WITH AGENT FUNCTION
# ============================================================================
def analyze_with_agent(query: str, image_bytes: bytes = None):
    """Analyze query using the MFGPlantIQ agent with optional image support."""
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=myEndpoint, credential=credential)
    
    results = {
        "final_response": "",
        "workflow_steps": [],
        "individual_agent_outputs": [],  # Store individual agent responses
        "debug_logs": [],
        "token_usage": {"input": 0, "output": 0, "total": 0}
    }
    
    with get_tracer().start_as_current_span("MFGPlantIQ-Analysis", kind=SpanKind.CLIENT) as current_span:
        trace_id = format_trace_id(current_span.get_span_context().trace_id)
        results["trace_id"] = trace_id
        
        with project_client:
            workflow = {
                "name": "MFGPlantIQ",
                "version": "1",
            }
            
            openai_client = project_client.get_openai_client()
            conversation = openai_client.conversations.create()
            results["debug_logs"].append(f"Created conversation (id: {conversation.id})")
            
            # Prepare input with image if provided
            input_content = query
            if image_bytes:
                # Encode image to base64 for the agent
                image_b64 = base64.b64encode(image_bytes).decode('utf-8')
                input_content = f"{query}\n\n[Image attached for analysis]"
                results["debug_logs"].append(f"Image attached: {len(image_bytes)} bytes")
            
            stream = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={"agent": {"name": workflow["name"], "type": "agent_reference"}},
                input=input_content,
                stream=True,
                metadata={"x-ms-debug-mode-enabled": "1"},
            )
            
            current_text = ""
            current_agent_id = None
            current_agent_output = ""
            
            for event in stream:
                if event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DONE:
                    results["final_response"] += event.text + "\n"
                    # Save to current agent if we have one
                    if current_agent_id:
                        results["individual_agent_outputs"].append({
                            "agent_id": current_agent_id,
                            "output": event.text,
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED and event.item.type == "workflow_action":
                    # New agent starting - save previous agent output if exists
                    if current_agent_id and current_agent_output:
                        results["individual_agent_outputs"].append({
                            "agent_id": current_agent_id,
                            "output": current_agent_output,
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                    current_agent_id = event.item.action_id
                    current_agent_output = ""
                    step_info = f"🔄 Agent '{event.item.action_id}' started"
                    results["workflow_steps"].append({
                        "action_id": event.item.action_id,
                        "status": "started",
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    results["debug_logs"].append(step_info)
                elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_DONE and event.item.type == "workflow_action":
                    # Agent completed - save its output
                    if current_agent_output:
                        results["individual_agent_outputs"].append({
                            "agent_id": event.item.action_id,
                            "output": current_agent_output,
                            "status": event.item.status,
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                        current_agent_output = ""
                    step_info = f"✅ Agent '{event.item.action_id}' completed (status: {event.item.status})"
                    results["workflow_steps"].append({
                        "action_id": event.item.action_id,
                        "status": event.item.status,
                        "previous_action": getattr(event.item, 'previous_action_id', None),
                        "timestamp": datetime.now().strftime("%H:%M:%S")
                    })
                    results["debug_logs"].append(step_info)
                elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DELTA:
                    current_text += event.delta
                    current_agent_output += event.delta
                else:
                    results["debug_logs"].append(f"Event: {event.type}")
            
            if current_text:
                results["final_response"] = current_text
            
            results["debug_logs"].append("Conversation completed")
    
    return results

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================
def initialize_session_state():
    """Initialize all session state variables."""
    defaults = {
        'chat_history': [],
        'agent_outputs': [],
        'debug_logs': [],
        'current_image': None,
        'current_image_bytes': None,
        'processing': False,
        'telemetry_initialized': False,
        'conversation_count': 0
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================
def add_debug_log(message: str, level: str = "INFO"):
    """Add a debug log entry."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message
    }
    st.session_state.debug_logs.append(log_entry)
    logger.info(f"[{level}] {message}")

def add_chat_message(role: str, content: str, image_data: bytes = None):
    """Add a message to chat history."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    message = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "image": image_data
    }
    st.session_state.chat_history.append(message)

def add_agent_output(output_type: str, content, trace_id: str = None):
    """Add agent output to the output panel."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    output = {
        "type": output_type,
        "content": content,
        "timestamp": timestamp,
        "trace_id": trace_id
    }
    st.session_state.agent_outputs.append(output)

def render_chat_message(message: dict):
    """Render a single chat message."""
    role = message["role"]
    content = message["content"]
    timestamp = message["timestamp"]
    image = message.get("image")
    
    if role == "user":
        st.markdown(f"""
        <div class="user-message">
            <div>{content}</div>
            <div class="timestamp">🕐 {timestamp}</div>
        </div>
        """, unsafe_allow_html=True)
        if image:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(image, caption="📎 Attached Image", use_container_width=True)
    else:
        st.markdown(f"""
        <div class="assistant-message">
            <div>{content}</div>
            <div class="timestamp">🕐 {timestamp}</div>
        </div>
        """, unsafe_allow_html=True)

def render_agent_output(output: dict):
    """Render agent output in the output panel."""
    output_type = output["type"]
    content = output["content"]
    timestamp = output["timestamp"]
    trace_id = output.get("trace_id")
    
    if output_type == "debug":
        st.markdown(f"""
        <div class="debug-message">
            <strong>🔧 Debug</strong> <span class="timestamp">{timestamp}</span><br>
            {content}
        </div>
        """, unsafe_allow_html=True)
    
    elif output_type == "workflow":
        st.markdown(f"""
        <div class="workflow-step">
            <strong>⚙️ Workflow Step</strong> <span class="timestamp">{timestamp}</span><br>
            Agent: <code>{content.get('action_id', 'N/A')}</code> | 
            Status: <span class="md-chip">{content.get('status', 'unknown')}</span>
        </div>
        """, unsafe_allow_html=True)
    
    elif output_type == "result":
        st.markdown(f"""
        <div style="margin-bottom: 12px;">
            <div class="md-chip md-chip-primary">🤖 PlantIQ Response</div>
            <span class="timestamp">{timestamp}</span>
        </div>
        """, unsafe_allow_html=True)
        
        if trace_id:
            st.markdown(f"""
            <div class="md-chip">🔗 Trace: {trace_id[:16]}...</div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Display the result content
        if isinstance(content, dict):
            # Show workflow steps
            if content.get("workflow_steps"):
                with st.expander("📋 Workflow Steps", expanded=False):
                    for step in content["workflow_steps"]:
                        status_icon = "✅" if step.get("status") == "completed" else "🔄"
                        st.markdown(f"{status_icon} **{step.get('action_id')}** - {step.get('status')} @ {step.get('timestamp')}")
            
            # Show main response
            st.markdown(content.get("final_response", "No response"))
        else:
            st.markdown(content)
    
    elif output_type == "error":
        st.error(f"❌ Error: {content}")

def process_user_input(user_input: str, image_bytes: bytes = None):
    """Process user input with the agent."""
    st.session_state.processing = True
    st.session_state.conversation_count += 1
    
    add_debug_log(f"Starting PlantIQ analysis for query: {user_input[:50]}...")
    if image_bytes:
        add_debug_log(f"Image attached: {len(image_bytes)} bytes")
    
    try:
        add_debug_log("Calling MFGPlantIQ agent...")
        results = analyze_with_agent(user_input, image_bytes)
        
        # Add workflow steps to output
        for step in results.get("workflow_steps", []):
            add_agent_output("workflow", step)
        
        # Add debug logs from agent
        for log in results.get("debug_logs", []):
            add_agent_output("debug", log)
        
        # Add final result to agent outputs (for individual agent details)
        add_agent_output("result", results, results.get("trace_id"))
        
        # Add summary to conversation history (left side)
        summary_text = results.get("final_response", "Analysis complete.")
        add_chat_message("assistant", summary_text)
        
        add_debug_log(f"Processing completed. Trace ID: {results.get('trace_id', 'N/A')}", "SUCCESS")
        
    except Exception as e:
        error_msg = str(e)
        add_debug_log(f"Error during processing: {error_msg}", "ERROR")
        add_agent_output("error", error_msg)
        add_chat_message("assistant", f"Sorry, an error occurred: {error_msg}")
    
    finally:
        st.session_state.processing = False

# ============================================================================
# MAIN UI FUNCTION
# ============================================================================
def main():
    """Main Streamlit application."""
    # Page configuration
    st.set_page_config(
        page_title="PlantIQ - Manufacturing Plant Design Platform",
        page_icon="🏭",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    
    # Apply Material Design 3 styling
    apply_material_design_3()
    
    # Initialize session state
    initialize_session_state()
    
    # Setup telemetry
    telemetry_status = setup_telemetry()
    
    # Header
    st.markdown("""
    <div style="text-align: center; padding: 20px 0 24px 0;">
        <div style="display: flex; align-items: center; justify-content: center; gap: 12px;">
            <span style="font-size: 40px;">🏭</span>
            <span class="plantiq-logo">PlantIQ</span>
        </div>
        <p class="plantiq-subtitle">Manufacturing Plant Design Platform | Powered by AI Agents</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Telemetry status indicator
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if telemetry_status:
            st.success("📊 Telemetry connected to Azure Foundry")
        else:
            st.warning("⚠️ Telemetry not connected")
    
    st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
    
    # Two-column layout with medium gap
    left_col, right_col = st.columns([1, 1], gap="medium")
    
    # =========================================================================
    # LEFT COLUMN - Chat History & Image Upload
    # =========================================================================
    with left_col:
        st.markdown("""
        <div class="md-header">
            💬 Chat & Upload
        </div>
        <div class="md-subheader">
            Upload plant diagrams and ask questions about your manufacturing setup
        </div>
        """, unsafe_allow_html=True)
        
        # Image upload section
        with st.expander("📤 Upload Plant Diagram", expanded=True):
            uploaded_file = st.file_uploader(
                "Choose a plant layout or diagram",
                type=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
                help="Upload an image of your manufacturing plant layout, P&ID diagram, or equipment schematic"
            )
            
            if uploaded_file is not None:
                image_bytes = uploaded_file.read()
                st.session_state.current_image = uploaded_file
                st.session_state.current_image_bytes = image_bytes
                
                st.image(image_bytes, caption="Preview", use_container_width=True)
                st.markdown(f"""
                <div class="md-chip">📁 {uploaded_file.name}</div>
                <div class="md-chip">📐 {len(image_bytes) / 1024:.1f} KB</div>
                """, unsafe_allow_html=True)
        
        st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
        
        # Chat history container
        st.markdown("""
        <div class="md-header">
            📜 Conversation History
        </div>
        """, unsafe_allow_html=True)
        
        chat_container = st.container(height=500)
        
        with chat_container:
            if not st.session_state.chat_history:
                st.markdown("""
                <div style="text-align: center; padding: 60px 20px; color: #72787E;">
                    <div style="font-size: 56px; margin-bottom: 16px;">🏭</div>
                    <div style="font-size: 16px; font-weight: 500;">Welcome to PlantIQ</div>
                    <div style="font-size: 13px; margin-top: 8px; line-height: 1.6;">
                        Upload a plant diagram or ask questions about:<br>
                        • Production line optimization<br>
                        • Equipment maintenance<br>
                        • Process flow analysis<br>
                        • Capacity planning
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                for message in st.session_state.chat_history:
                    render_chat_message(message)
        
        # Processing indicator
        if st.session_state.processing:
            st.markdown("""
            <div class="status-processing">
                <span>⏳</span> PlantIQ is analyzing your request...
            </div>
            """, unsafe_allow_html=True)
            st.progress(0.5, text="Agent workflow in progress...")
    
    # =========================================================================
    # RIGHT COLUMN - Agent Output
    # =========================================================================
    with right_col:
        st.markdown("""
        <div class="md-header">
            🤖 Agent Output
        </div>
        <div class="md-subheader">
            View analysis results, workflow steps, and debug information
        </div>
        """, unsafe_allow_html=True)
        
        # Debug toggle
        show_debug = st.toggle("🔧 Show Debug Logs", value=False)
        
        output_container = st.container(height=500)
        
        with output_container:
            # Show debug logs if enabled
            if show_debug and st.session_state.debug_logs:
                st.markdown("### 🔧 Debug Logs")
                for log in st.session_state.debug_logs[-15:]:
                    level_color = {
                        "INFO": "#1565C0",
                        "SUCCESS": "#2E7D32",
                        "ERROR": "#BA1A1A",
                        "WARNING": "#F57C00"
                    }.get(log["level"], "#72787E")
                    
                    st.markdown(f"""
                    <div class="debug-message">
                        <span style="color: {level_color}; font-weight: bold;">[{log["level"]}]</span>
                        <span class="timestamp">{log["timestamp"]}</span><br>
                        {log["message"]}
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown("---")
            
            # Show agent outputs
            if not st.session_state.agent_outputs:
                st.markdown("""
                <div style="text-align: center; padding: 60px 20px; color: #72787E;">
                    <div style="font-size: 56px; margin-bottom: 16px;">⚙️</div>
                    <div style="font-size: 16px; font-weight: 500;">No Analysis Yet</div>
                    <div style="font-size: 13px; margin-top: 8px;">
                        Agent responses and workflow steps will appear here
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Find the latest result output for summary
                result_outputs = [o for o in st.session_state.agent_outputs if o["type"] == "result"]
                
                if result_outputs:
                    latest_result = result_outputs[-1]
                    content = latest_result["content"]
                    timestamp = latest_result["timestamp"]
                    trace_id = latest_result.get("trace_id", "")
                    
                    # Show trace info header
                    if trace_id:
                        st.markdown(f"""
                        <div class="info-card">
                            <div class="md-chip">🔗 Trace: {trace_id[:16]}...</div>
                            <span class="timestamp">{timestamp}</span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # Show individual agent outputs as expanders
                    if isinstance(content, dict) and content.get("individual_agent_outputs"):
                        st.markdown("""
                        <div class="md-header" style="font-size: 16px; margin-top: 8px;">
                            🔍 Individual Agent Outputs
                        </div>
                        <div class="md-subheader">
                            Click to expand each agent's detailed response
                        </div>
                        """, unsafe_allow_html=True)
                        
                        for idx, agent_output in enumerate(content["individual_agent_outputs"]):
                            agent_id = agent_output.get("agent_id", f"Agent {idx + 1}")
                            agent_text = agent_output.get("output", "No output")
                            agent_time = agent_output.get("timestamp", "")
                            agent_status = agent_output.get("status", "completed")
                            
                            status_icon = "✅" if agent_status == "completed" else "🔄"
                            
                            with st.expander(f"{status_icon} {agent_id} @ {agent_time}", expanded=False):
                                st.markdown(agent_text)
                        
                        st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
                    
                    # Show workflow steps as expander
                    if isinstance(content, dict) and content.get("workflow_steps"):
                        with st.expander("📋 Workflow Steps", expanded=False):
                            for step in content["workflow_steps"]:
                                status_icon = "✅" if step.get("status") == "completed" else "🔄"
                                st.markdown(f"{status_icon} **{step.get('action_id')}** - {step.get('status')} @ {step.get('timestamp')}")
                    
                    # Show message if no individual outputs captured
                    if isinstance(content, dict) and not content.get("individual_agent_outputs"):
                        st.info("ℹ️ No individual agent outputs captured for this analysis.")
    
    # =========================================================================
    # CHAT INPUT (Bottom)
    # =========================================================================
    st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
    
    # Chat input
    user_input = st.chat_input(
        placeholder="Ask about production lines, equipment, maintenance, capacity planning...",
        disabled=st.session_state.processing
    )
    
    if user_input:
        # Add user message to chat
        add_chat_message("user", user_input, st.session_state.current_image_bytes)
        
        # Add debug output
        add_agent_output("debug", f"User query: {user_input}")
        
        # Process with progress
        with st.spinner("🔄 PlantIQ is analyzing..."):
            process_user_input(user_input, st.session_state.current_image_bytes)
        
        # Rerun to update UI
        st.rerun()
    
    # =========================================================================
    # SIDEBAR - Additional Controls
    # =========================================================================
    with st.sidebar:
        st.markdown("### ⚙️ PlantIQ Settings")
        
        st.markdown("---")
        
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.agent_outputs = []
            st.session_state.debug_logs = []
            st.rerun()
        
        if st.button("🖼️ Clear Image", use_container_width=True):
            st.session_state.current_image = None
            st.session_state.current_image_bytes = None
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📊 Session Statistics")
        st.metric("Conversations", st.session_state.conversation_count)
        st.metric("Messages", len(st.session_state.chat_history))
        st.metric("Agent Outputs", len(st.session_state.agent_outputs))
        
        st.markdown("---")
        st.markdown("### 🔗 Telemetry Status")
        if st.session_state.telemetry_initialized:
            st.success("✅ Connected to Foundry")
        else:
            st.warning("⚠️ Not connected")
        
        st.markdown("---")
        st.markdown("""
        <div style="text-align: center; color: #72787E; font-size: 11px;">
            PlantIQ v1.0<br>
            Powered by Azure AI Foundry
        </div>
        """, unsafe_allow_html=True)

# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    main()