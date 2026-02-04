import asyncio
import logging
import streamlit as st
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from agent_framework import ChatMessage, Content, Role, ChatAgent
from agent_framework.azure import AzureAIAgentClient
from agent_framework.observability import get_tracer
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from pydantic import Field
import os
from dotenv import load_dotenv
from PIL import Image
import io
import base64
from datetime import datetime

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
        /* Material Design 3 Color Palette */
        :root {
            --md-sys-color-primary: #6750A4;
            --md-sys-color-on-primary: #FFFFFF;
            --md-sys-color-primary-container: #EADDFF;
            --md-sys-color-on-primary-container: #21005D;
            --md-sys-color-secondary: #625B71;
            --md-sys-color-on-secondary: #FFFFFF;
            --md-sys-color-secondary-container: #E8DEF8;
            --md-sys-color-surface: #FEF7FF;
            --md-sys-color-surface-variant: #E7E0EC;
            --md-sys-color-on-surface: #1D1B20;
            --md-sys-color-on-surface-variant: #49454F;
            --md-sys-color-outline: #79747E;
            --md-sys-color-outline-variant: #CAC4D0;
            --md-sys-color-error: #B3261E;
            --md-sys-color-success: #2E7D32;
        }
        
        /* Main app background */
        .stApp {
            background-color: var(--md-sys-color-surface);
        }
        
        /* Container styling */
        .chat-container {
            background-color: white;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
            margin-bottom: 16px;
        }
        
        .output-container {
            background-color: white;
            border-radius: 16px;
            padding: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
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
            background-color: #FFF3E0;
            border-left: 4px solid #FF9800;
            padding: 8px 12px;
            margin: 4px 0;
            border-radius: 0 8px 8px 0;
            font-family: monospace;
            font-size: 12px;
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
            font-weight: 500;
            font-size: 22px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        /* Subheader */
        .md-subheader {
            color: var(--md-sys-color-on-surface-variant);
            font-size: 14px;
            margin-bottom: 12px;
        }
        
        /* Image preview */
        .image-preview {
            border-radius: 12px;
            overflow: hidden;
            margin: 8px 0;
            border: 1px solid var(--md-sys-color-outline-variant);
        }
        
        /* Status indicators */
        .status-processing {
            color: var(--md-sys-color-primary);
            font-weight: 500;
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
        
        /* Code block styling */
        .stCodeBlock {
            border-radius: 12px !important;
        }
        
        /* Progress bar customization */
        .stProgress > div > div > div {
            background-color: var(--md-sys-color-primary);
        }
        
        /* File uploader styling */
        .stFileUploader {
            border: 2px dashed var(--md-sys-color-outline-variant);
            border-radius: 12px;
            padding: 16px;
        }
        
        /* Divider */
        .md-divider {
            height: 1px;
            background-color: var(--md-sys-color-outline-variant);
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
        }
        
        /* Hide Streamlit branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Custom scrollbar */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: var(--md-sys-color-surface-variant);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb {
            background: var(--md-sys-color-outline);
            border-radius: 4px;
        }
        
        ::-webkit-scrollbar-thumb:hover {
            background: var(--md-sys-color-on-surface-variant);
        }
    </style>
    """, unsafe_allow_html=True)

# Async function to analyze image with agent
async def analyze_with_agent(question: str, image_bytes: bytes):
    """Analyze pipeline image using the Azure AI Foundry agent."""
    myEndpoint = os.getenv("AZURE_AI_PROJECT") or os.getenv("AZURE_AI_PROJECTS_ENDPOINT")
    
    if not myEndpoint:
        raise ValueError("Missing project endpoint. Set AZURE_AI_PROJECT in your .env file.")
    
    # Get the existing agent from Azure AI Foundry
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )
    myAgent = "diagramagent"
    with get_tracer().start_as_current_span("diagramagent", kind=SpanKind.CLIENT) as current_span:
        print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")

        agent_info = project_client.agents.get(agent_name=myAgent)
        
        # Create agent using agent-framework with proper cleanup
        credential = DefaultAzureCredential()
        
        async with AzureAIAgentClient(
            credential=credential,
            project_endpoint=myEndpoint
        ) as chat_client:
                
                agent = ChatAgent(
                    chat_client=chat_client,
                    name=agent_info.name,
                    instructions="""You are a IT infrastructure specialist, you job is to analyze the image and find the resource used
                    and build a terra form script to deploy the same infrastructure in azure cloud.
                    1. Analyze the image and identify the resources used.
                    2. Generate a terraform script to deploy the same infrastructure in azure cloud.
                    3. Provide the terraform script as output.
                    Create terraform script for all the resources you find in the image.
                    
                    """
                )
                
                # Create ChatMessage with text and image content
                message = ChatMessage(
                    role=Role.USER,
                    contents=[
                        Content.from_text(question),
                        Content.from_data(
                            data=image_bytes,
                            media_type="image/jpeg"
                        )
                    ]
                )
                
                # Run the agent
                result = await agent.run(message)
                
                # Extract token usage information from usage_details
                token_usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
                
                # Access usage_details attribute (agent_framework._types.UsageDetails is a TypedDict)
                if hasattr(result, 'usage_details') and result.usage_details:
                    usage_details = result.usage_details
                    print(f"Found usage_details: {usage_details}")
                    
                    # Extract token counts from UsageDetails TypedDict using dictionary access
                    token_usage["prompt_tokens"] = usage_details.get('input_token_count', 0) or 0
                    token_usage["completion_tokens"] = usage_details.get('output_token_count', 0) or 0
                    token_usage["total_tokens"] = usage_details.get('total_token_count', 0) or 0
                    
                    # Calculate total if not provided
                    #if token_usage["total_tokens"] == 0 and (token_usage["prompt_tokens"] > 0 or token_usage["completion_tokens"] > 0):
                    #    token_usage["total_tokens"] = token_usage["prompt_tokens"] + token_usage["completion_tokens"]
                    
                    print(f"Extracted token usage: {token_usage}")
                else:
                    print(f"Warning: usage_details not found in result. Result attributes: {dir(result) if hasattr(result, '__dir__') else 'N/A'}")
                
                return result.text, token_usage
        
def imgscreen():
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )

    # This will enable tracing and configure the application to send telemetry data to the
    # Application Insights instance attached to the Azure AI project.
    # This will override any existing configuration.
    try:
        conn_string = project_client.telemetry.get_application_insights_connection_string()
    except Exception:
        logger.warning(
            "No Application Insights connection string found for the Azure AI Project. "
            "Please ensure Application Insights is configured in your Azure AI project, "
            "or call configure_otel_providers() manually with custom exporters."
        )
        return
    configure_azure_monitor(
        connection_string=conn_string,
        enable_live_metrics=True,
        resource=create_resource(),
        enable_performance_counters=False,
    )
    # This call is not necessary if you have the environment variable ENABLE_INSTRUMENTATION=true set
    # If not or set to false, or if you want to enable or disable sensitive data collection, call this function.
    enable_instrumentation(enable_sensitive_data=True)
    print("Observability is set up. Starting Diagram Agent...")

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
        logger.info("Telemetry initialized successfully")
        return True
    except Exception as e:
        logger.warning(f"Could not initialize telemetry: {e}")
        return False

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================
def initialize_session_state():
    """Initialize all session state variables."""
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'agent_outputs' not in st.session_state:
        st.session_state.agent_outputs = []
    if 'debug_logs' not in st.session_state:
        st.session_state.debug_logs = []
    if 'current_image' not in st.session_state:
        st.session_state.current_image = None
    if 'current_image_bytes' not in st.session_state:
        st.session_state.current_image_bytes = None
    if 'processing' not in st.session_state:
        st.session_state.processing = False
    if 'telemetry_initialized' not in st.session_state:
        st.session_state.telemetry_initialized = False

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

def add_agent_output(output_type: str, content: str, token_usage: dict = None, trace_id: str = None):
    """Add agent output to the output panel."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    output = {
        "type": output_type,
        "content": content,
        "timestamp": timestamp,
        "token_usage": token_usage,
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
            <div class="timestamp">{timestamp}</div>
        </div>
        """, unsafe_allow_html=True)
        if image:
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                st.image(image, width='stretch', caption="Uploaded Image")
    else:
        st.markdown(f"""
        <div class="assistant-message">
            <div>{content}</div>
            <div class="timestamp">{timestamp}</div>
        </div>
        """, unsafe_allow_html=True)

def render_agent_output(output: dict):
    """Render agent output in the output panel."""
    output_type = output["type"]
    content = output["content"]
    timestamp = output["timestamp"]
    token_usage = output.get("token_usage")
    trace_id = output.get("trace_id")
    
    if output_type == "debug":
        st.markdown(f"""
        <div class="debug-message">
            <strong>🔧 Debug</strong> <span class="timestamp">{timestamp}</span><br>
            {content}
        </div>
        """, unsafe_allow_html=True)
    elif output_type == "result":
        st.markdown(f"""
        <div style="margin-bottom: 12px;">
            <div class="md-chip">🤖 Agent Response</div>
            <span class="timestamp">{timestamp}</span>
        </div>
        """, unsafe_allow_html=True)
        
        # Show token usage if available
        if token_usage:
            cols = st.columns(3)
            with cols[0]:
                st.metric("Input Tokens", token_usage.get("prompt_tokens", 0))
            with cols[1]:
                st.metric("Output Tokens", token_usage.get("completion_tokens", 0))
            with cols[2]:
                st.metric("Total Tokens", token_usage.get("total_tokens", 0))
        
        if trace_id:
            st.markdown(f"""
            <div class="md-chip">🔗 Trace: {trace_id[:16]}...</div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown(content)
    elif output_type == "error":
        st.error(f"❌ Error: {content}")

async def process_user_input(user_input: str, image_bytes: bytes):
    """Process user input with the agent."""
    st.session_state.processing = True
    
    # Add debug log
    add_debug_log(f"Starting agent processing for query: {user_input[:50]}...")
    add_debug_log(f"Image size: {len(image_bytes)} bytes")
    
    try:
        # Run the agent
        add_debug_log("Calling analyze_with_agent...")
        result_text, token_usage = await analyze_with_agent(user_input, image_bytes)
        
        # Get trace ID from current span
        tracer = get_tracer()
        trace_id = "N/A"
        
        add_debug_log(f"Agent completed. Tokens used: {token_usage.get('total_tokens', 0)}")
        
        # Add results
        add_agent_output("result", result_text, token_usage, trace_id)
        add_chat_message("assistant", "Analysis complete. See the output panel for detailed results.")
        
        add_debug_log("Processing completed successfully", "SUCCESS")
        
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
        page_title="AI Image Analyzer",
        page_icon="🖼️",
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
    <div style="text-align: center; padding: 20px 0 30px 0;">
        <h1 style="color: #6750A4; margin: 0;">🖼️ AI Image Analyzer</h1>
        <p style="color: #49454F; margin-top: 8px;">Infrastructure Analysis & Terraform Generation Agent</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Telemetry status indicator
    if telemetry_status:
        st.success("✅ Telemetry connected to Azure Foundry", icon="📊")
    else:
        st.warning("⚠️ Telemetry not connected", icon="📊")
    
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
            Upload an image and ask questions about your infrastructure
        </div>
        """, unsafe_allow_html=True)
        
        # Image upload section
        with st.expander("📤 Upload Image", expanded=True):
            uploaded_file = st.file_uploader(
                "Choose an infrastructure diagram",
                type=["png", "jpg", "jpeg", "gif", "webp"],
                help="Upload an image of your infrastructure diagram for analysis"
            )
            
            if uploaded_file is not None:
                # Read and store image
                image_bytes = uploaded_file.read()
                st.session_state.current_image = uploaded_file
                st.session_state.current_image_bytes = image_bytes
                
                # Show preview
                st.image(image_bytes, caption="Preview", width='stretch')
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
                <div style="text-align: center; padding: 40px; color: #79747E;">
                    <div style="font-size: 48px; margin-bottom: 16px;">💭</div>
                    <div>No messages yet</div>
                    <div style="font-size: 12px; margin-top: 8px;">
                        Upload an image and start asking questions!
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
                ⏳ Processing your request...
            </div>
            """, unsafe_allow_html=True)
            st.progress(0.5, text="Agent is analyzing...")
    
    # =========================================================================
    # RIGHT COLUMN - Agent Output
    # =========================================================================
    with right_col:
        st.markdown("""
        <div class="md-header">
            🤖 Agent Output
        </div>
        <div class="md-subheader">
            View detailed analysis results and debug information
        </div>
        """, unsafe_allow_html=True)
        
        # Debug toggle
        show_debug = st.toggle("🔧 Show Debug Logs", value=False)
        
        output_container = st.container(height=500)
        
        with output_container:
            # Show debug logs if enabled
            if show_debug and st.session_state.debug_logs:
                st.markdown("### 🔧 Debug Logs")
                for log in st.session_state.debug_logs[-20:]:  # Show last 20 logs
                    level_color = {
                        "INFO": "#2196F3",
                        "SUCCESS": "#4CAF50",
                        "ERROR": "#F44336",
                        "WARNING": "#FF9800"
                    }.get(log["level"], "#757575")
                    
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
                <div style="text-align: center; padding: 40px; color: #79747E;">
                    <div style="font-size: 48px; margin-bottom: 16px;">🤖</div>
                    <div>No output yet</div>
                    <div style="font-size: 12px; margin-top: 8px;">
                        Agent responses will appear here
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                for output in st.session_state.agent_outputs:
                    render_agent_output(output)
                    st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
    
    # =========================================================================
    # CHAT INPUT (Bottom)
    # =========================================================================
    st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
    
    # Check if image is uploaded
    if st.session_state.current_image_bytes is None:
        st.info("📤 Please upload an image first before asking questions.")
    
    # Chat input
    user_input = st.chat_input(
        placeholder="Ask about your infrastructure diagram...",
        disabled=st.session_state.processing or st.session_state.current_image_bytes is None
    )
    
    if user_input and st.session_state.current_image_bytes:
        # Add user message to chat
        add_chat_message("user", user_input, st.session_state.current_image_bytes)
        
        # Add debug output
        add_agent_output("debug", f"User query: {user_input}")
        
        # Process with progress
        with st.spinner("🔄 Agent is analyzing your image..."):
            asyncio.run(process_user_input(user_input, st.session_state.current_image_bytes))
        
        # Rerun to update UI
        st.rerun()
    
    # =========================================================================
    # SIDEBAR - Additional Controls
    # =========================================================================
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        
        if st.button("🗑️ Clear Chat History", width='stretch'):
            st.session_state.chat_history = []
            st.session_state.agent_outputs = []
            st.session_state.debug_logs = []
            st.rerun()
        
        if st.button("🖼️ Clear Image", width='stretch'):
            st.session_state.current_image = None
            st.session_state.current_image_bytes = None
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📊 Session Stats")
        st.metric("Messages", len(st.session_state.chat_history))
        st.metric("Agent Outputs", len(st.session_state.agent_outputs))
        st.metric("Debug Logs", len(st.session_state.debug_logs))
        
        st.markdown("---")
        st.markdown("### 🔗 Telemetry")
        if st.session_state.telemetry_initialized:
            st.success("Connected to Foundry")
        else:
            st.warning("Not connected")

# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    main()