import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from random import randint
import re
from typing import Annotated, Dict, List, Any
import requests
import streamlit as st
from utils import get_weather, fetch_stock_data
import io
import sys
import time
from openai import OpenAI, AzureOpenAI

from agent_framework import ChatAgent, ChatMessage
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework import observability
from pydantic import Field
from azure.ai.agents.models import FileInfo, VectorStore
from azure.ai.agents.models import AzureAISearchTool, AzureAISearchQueryType
from azure.ai.projects.models import ConnectionType
from exagent import existingagent
from agenteval import agenteval
from redteam import redteam_main

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

myEndpoint = os.getenv("AZURE_AI_PROJECT")
async def existingagent(query):
    """
    Execute agent query and return structured results
    Returns: dict with response_text, citations, mcp_calls, and usage info
    """
    async with AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    ) as project_client:
        

        def extract_response_text(raw):
            raw = str(raw)
            m = re.search(r"ResponseOutputText\(.*?text='([^']+)'", raw, re.DOTALL)
            return m.group(1) if m else None

        myAgent = "skitagent"
        result = {
            "response_text": "",
            "citations": [],
            "mcp_calls": [],
            "agent_outputs": {},
            "status": "processing",
            "trace_id": "",
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
        
        with observability.get_tracer().start_as_current_span("skitagent", kind=SpanKind.CLIENT) as current_span:
            trace_id = format_trace_id(current_span.get_span_context().trace_id)
            result["trace_id"] = trace_id
            
            # Get an existing agent
            agent = await project_client.agents.get(agent_name=myAgent)
            result["agent_outputs"]["main"] = f"Retrieved agent: {agent.name}"

            openai_client = project_client.get_openai_client()

            # Reference the agent to get a response
            response = await openai_client.responses.create(
                input=[{"role": "user", "content": query}],
                extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
            )

            # Check if there are MCP approval requests
            mcp_approval_requests = []
            for output_item in response.output:
                if hasattr(output_item, 'type') and output_item.type == 'mcp_approval_request':
                    mcp_approval_requests.append(output_item)

            # Auto-approve all MCP tool calls
            if mcp_approval_requests:
                for approval_request in mcp_approval_requests:
                    response = await openai_client.responses.create(
                    previous_response_id=response.id,
                    input=[{
                        "type": "mcp_approval_response",
                        "approve": True,
                        "approval_request_id": approval_request.id
                    }],
                        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}}
                    )
                
                # Poll for the final result
                max_retries = 30
                retry_count = 0
                
                while retry_count < max_retries:
                    response = await openai_client.responses.retrieve(response_id=response.id)
                    
                    if response.status == 'completed':
                        result["status"] = "completed"
                        break
                    elif response.status == 'failed':
                        result["status"] = "failed"
                        if response.error:
                            result["error"] = str(response.error)
                        break
                    else:
                        await asyncio.sleep(2)
                        retry_count += 1

            # Extract the final result with citations
            response_texts = []
            for output_item in response.output:
                item_type = getattr(output_item, 'type', None)
                
                # Check for message output (ResponseOutputMessage)
                if item_type == 'message':
                    if hasattr(output_item, 'content') and output_item.content:
                        for content_item in output_item.content:
                            if hasattr(content_item, 'text'):
                                response_texts.append(content_item.text)
                                
                                # Extract citations if available
                                if hasattr(content_item, 'annotations') and content_item.annotations:
                                    for annotation in content_item.annotations:
                                        citation_info = {
                                            "text": getattr(annotation, 'text', 'Citation'),
                                            "file_name": "",
                                            "quote": ""
                                        }
                                        if hasattr(annotation, 'file_citation'):
                                            citation = annotation.file_citation
                                            citation_info["file_name"] = getattr(citation, 'file_name', 'N/A')
                                            citation_info["quote"] = getattr(citation, 'quote', '')
                                        result["citations"].append(citation_info)
                
                # Check for direct text output (older format)
                elif item_type == 'response_output_text':
                    response_texts.append(output_item.text)
                    
                    # Extract citations if available
                    if hasattr(output_item, 'annotations') and output_item.annotations:
                        for annotation in output_item.annotations:
                            citation_info = {
                                "text": getattr(annotation, 'text', 'Citation'),
                                "file_name": "",
                                "quote": ""
                            }
                            if hasattr(annotation, 'file_citation'):
                                citation = annotation.file_citation
                                citation_info["file_name"] = getattr(citation, 'file_name', 'N/A')
                                citation_info["quote"] = getattr(citation, 'quote', '')
                            result["citations"].append(citation_info)
                
                # Check for MCP call results
                elif item_type == 'mcp_call':
                    mcp_info = {
                        "tool": output_item.name,
                        "status": output_item.status,
                        "output": ""
                    }
                    if hasattr(output_item, 'output') and output_item.output:
                        output_text = str(output_item.output)
                        mcp_info["output"] = output_text[:1000] if len(output_text) > 1000 else output_text
                    result["mcp_calls"].append(mcp_info)

            result["response_text"] = "\n\n".join(response_texts)

            print("Agent Response Text:", response)
            
            # Extract usage information - try multiple field name variations
            if hasattr(response, 'usage') and response.usage:
                usage_obj = response.usage
                # Try different field name variations
                result["usage"]["prompt_tokens"] = (
                    getattr(usage_obj, 'prompt_tokens', None) or 
                    getattr(usage_obj, 'input_tokens', None) or 
                    0
                )
                result["usage"]["completion_tokens"] = (
                    getattr(usage_obj, 'completion_tokens', None) or 
                    getattr(usage_obj, 'output_tokens', None) or 
                    0
                )
                result["usage"]["total_tokens"] = (
                    getattr(usage_obj, 'total_tokens', None) or 
                    (result["usage"]["prompt_tokens"] + result["usage"]["completion_tokens"]) or
                    0
                )
                result["agent_outputs"]["usage_obj"] = f"Usage: {usage_obj}"
            
            # Also check usage_details
            if hasattr(response, 'usage_details') and response.usage_details:
                usage_details = response.usage_details
                if result["usage"]["prompt_tokens"] == 0:
                    result["usage"]["prompt_tokens"] = getattr(usage_details, 'prompt_tokens', 0) or getattr(usage_details, 'input_tokens', 0)
                if result["usage"]["completion_tokens"] == 0:
                    result["usage"]["completion_tokens"] = getattr(usage_details, 'completion_tokens', 0) or getattr(usage_details, 'output_tokens', 0)
                if result["usage"]["total_tokens"] == 0:
                    result["usage"]["total_tokens"] = getattr(usage_details, 'total_tokens', 0)
                result["agent_outputs"]["usage_details_obj"] = f"Usage details: {usage_details}"
            
            # Debug: Show all attributes
            result["agent_outputs"]["usage_debug"] = f"Has usage: {hasattr(response, 'usage')}, Has usage_details: {hasattr(response, 'usage_details')}"
            
        return result

#now lets process the video
def createvideo(query):
    """
    Generate video using Azure OpenAI Sora via direct API calls
    Returns: path to the generated video file
    """
    # 1. Setup
    endpoint = os.getenv("SORA_ENDPOINT")
    api_key = os.getenv("SORA_API_KEY")
    api_version = "preview"
    deployment_name = "sora-2"  # Your Sora deployment name
    
    # 2. Video generation parameters
    prompt = query[:1000]  # Limit prompt length to avoid issues
    
    # 3. Construct the Azure-specific endpoint URL
    # Remove trailing slashes and /openai from endpoint if present
    base_endpoint = endpoint.rstrip('/')
    if base_endpoint.endswith('/openai'):
        base_endpoint = base_endpoint[:-7]
    
    # Format: https://{resource}.cognitiveservices.azure.com/openai/deployments/{deployment}/videos?api-version={version}
    create_url = f"{base_endpoint}/openai/v1/videos?api-version={api_version}"
    
    headers = {
        # "api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": deployment_name,  # Required: model/deployment name
        "prompt": prompt,
        "size": "1280x720",
        # "second": 8,
        # Note: duration/seconds might not be supported yet in preview
    }
    
    print(f"Creating video with URL: {create_url}")
    print(f"Payload: {payload}")
    
    # 4. Create video generation request
    response = requests.post(create_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        raise Exception(f"Video creation failed: {response.status_code} - {response.text}")
    
    result = response.json()
    task_id = result.get("id")
    
    if not task_id:
        raise Exception(f"No task ID returned: {result}")
    
    print(f"Task created: {task_id}")
    
    # 5. Poll for completion
    retrieve_url = f"{base_endpoint}/openai/v1/videos/{task_id}?api-version={api_version}"
    
    poll_count = 0
    max_polls = 36  # 6 minutes max (36 * 10 seconds)
    
    while poll_count < max_polls:
        status_response = requests.get(retrieve_url, headers=headers)
        
        print(f"Checking status at: {retrieve_url}, Response code: {status_response.status_code}")
        
        if status_response.status_code != 200:
            raise Exception(f"Status check failed: {status_response.status_code} - {status_response.text}")
        
        status_data = status_response.json()
        status = status_data.get("status")
        
        print(f"Status: {status}")
        
        if status == "completed":
            # Video is ready - we need to download it using the content endpoint
            print(f"Video generation completed! ID: {task_id}")
            break
        elif status in ["failed", "cancelled"]:
            error_msg = status_data.get("error", "Unknown error")
            raise Exception(f"Video generation failed: {error_msg}")
        else:
            time.sleep(10)
            poll_count += 1
    
    if poll_count >= max_polls:
        raise Exception("Video generation timed out after 6 minutes")

    # 5. Download the video content
    # The video content is available at a separate endpoint
    content_url = f"{base_endpoint}/openai/v1/videos/{task_id}/content?api-version={api_version}"
    
    print(f"Downloading video from: {content_url}")
    
    video_response = requests.get(content_url, headers=headers)
    
    if video_response.status_code != 200:
        raise Exception(f"Video download failed: {video_response.status_code} - {video_response.text}")
    
    # 6. Save the video
    # Create videos directory if it doesn't exist
    videos_dir = Path("videos")
    videos_dir.mkdir(exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = videos_dir / f"skit_video_{timestamp}.mp4"

    # Save video content
    with open(output_path, "wb") as f:
        f.write(video_response.content)
    
    print(f"Video saved to: {output_path}")

    return str(output_path)

# Set up Streamlit page configuration
st.set_page_config(
    page_title="AI Enable Skit Making", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Material Design 3 color scheme
MD3_COLORS = {
    "primary": "#6750A4",
    "secondary": "#625B71",
    "tertiary": "#7D5260",
    "surface": "#FFFBFE",
    "surface_variant": "#E7E0EC",
    "on_surface": "#1C1B1F",
    "outline": "#79747E",
    "background": "#FFFBFE",
    "success": "#4CAF50",
    "error": "#B3261E"
}

# Custom CSS for Material Design 3
def apply_md3_styling():
    st.markdown(f"""
    <style>
        /* Import Material Symbols */
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0');
        
        /* Global Styles */
        * {{
            font-family: 'Roboto', sans-serif;
        }}
        
        .stApp {{
            background-color: {MD3_COLORS['background']};
        }}
        
        /* Title Styling */
        h1 {{
            color: {MD3_COLORS['primary']};
            font-weight: 500;
            margin-bottom: 2rem;
        }}
        
        /* Container Styling */
        .main-container {{
            background-color: {MD3_COLORS['surface']};
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        }}
        
        /* Chat Container */
        .chat-container {{
            background-color: white;
            border-radius: 12px;
            border: 1px solid {MD3_COLORS['outline']};
            padding: 16px;
            height: 500px;
            overflow-y: auto;
        }}
        
        /* Message Bubbles */
        .user-message {{
            background-color: {MD3_COLORS['primary']};
            color: white;
            padding: 12px 16px;
            border-radius: 18px 18px 4px 18px;
            margin: 8px 0;
            max-width: 80%;
            float: right;
            clear: both;
        }}
        
        .agent-message {{
            background-color: {MD3_COLORS['surface_variant']};
            color: {MD3_COLORS['on_surface']};
            padding: 12px 16px;
            border-radius: 18px 18px 18px 4px;
            margin: 8px 0;
            max-width: 80%;
            float: left;
            clear: both;
        }}
        
        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            gap: 8px;
        }}
        
        .stTabs [data-baseweb="tab"] {{
            background-color: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
            padding: 8px 16px;
            color: {MD3_COLORS['on_surface']};
        }}
        
        .stTabs [aria-selected="true"] {{
            background-color: {MD3_COLORS['primary']};
            color: white;
        }}
        
        /* Input Styling */
        .stTextInput input {{
            border-radius: 8px;
            border: 1px solid {MD3_COLORS['outline']};
            padding: 12px;
        }}
        
        /* Button Styling */
        .stButton button {{
            background-color: {MD3_COLORS['primary']};
            color: white;
            border-radius: 20px;
            padding: 10px 24px;
            border: none;
            font-weight: 500;
            transition: all 0.3s ease;
        }}
        
        .stButton button:hover {{
            background-color: {MD3_COLORS['secondary']};
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }}
        
        /* Expander */
        .streamlit-expanderHeader {{
            background-color: {MD3_COLORS['surface_variant']};
            border-radius: 8px;
            font-weight: 500;
        }}
        
        /* Metric Cards */
        .metric-card {{
            background-color: {MD3_COLORS['surface_variant']};
            border-radius: 12px;
            padding: 16px;
            margin: 8px 0;
        }}
        
        /* Status Badge */
        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }}
        
        .status-success {{
            background-color: {MD3_COLORS['success']};
            color: white;
        }}
        
        .status-error {{
            background-color: {MD3_COLORS['error']};
            color: white;
        }}
    </style>
    """, unsafe_allow_html=True)

def skitmain():
    apply_md3_styling()
    
    # Initialize session state
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'agent_results' not in st.session_state:
        st.session_state.agent_results = []
    if 'total_usage' not in st.session_state:
        st.session_state.total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0
        }
    if 'generated_video' not in st.session_state:
        st.session_state.generated_video = None
    if 'video_generating' not in st.session_state:
        st.session_state.video_generating = False
    
    # Header
    st.markdown("<h1>🎭 STSKit - Skit Maker</h1>", unsafe_allow_html=True)
    st.markdown("Create engaging skits using AI agents with Material Design 3", unsafe_allow_html=False)
    
    # Create two columns with medium gap
    col1, col2 = st.columns([1, 1], gap="medium")
    
    with col1:
        st.markdown("### 💬 Agent Conversation")
        
        # Chat container with fixed height
        chat_container = st.container(height=500)
        
        with chat_container:
            # Display chat history
            for message in st.session_state.chat_history:
                if message['role'] == 'user':
                    st.markdown(f"""
                    <div style="text-align: right; margin-bottom: 16px;">
                        <div class="user-message">
                            <strong>You:</strong><br>{message['content']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="margin-bottom: 16px;">
                        <div class="agent-message">
                            <strong>Agent:</strong><br>{message['content']}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 📊 Agent Details")
        
        # Create tabs for different outputs
        tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Agent Output", "🔧 MCP Calls", "📚 Citations", "📈 Token Usage", "🎬 Video"])
        
        with tab1:
            st.markdown("**Individual Agent Outputs**")
            if st.session_state.agent_results:
                latest_result = st.session_state.agent_results[-1]
                
                with st.container(height=450):
                    # Status badge
                    status = latest_result.get('status', 'unknown')
                    status_class = 'status-success' if status == 'completed' else 'status-error'
                    st.markdown(f'<span class="status-badge {status_class}">{status.upper()}</span>', 
                              unsafe_allow_html=True)
                    
                    # Trace ID
                    if latest_result.get('trace_id'):
                        st.markdown(f"**Trace ID:** `{latest_result['trace_id']}`")
                    
                    st.markdown("---")
                    
                    # Response text
                    if latest_result.get('response_text'):
                        st.markdown("**Response:**")
                        st.markdown(latest_result['response_text'])
                    
                    # Agent specific outputs
                    if latest_result.get('agent_outputs'):
                        st.markdown("---")
                        st.markdown("**Agent Logs:**")
                        for key, value in latest_result['agent_outputs'].items():
                            with st.expander(f"🤖 {key.upper()}"):
                                st.text(value)
            else:
                st.info("No agent output yet. Start a conversation to see results!")
        
        with tab2:
            st.markdown("**MCP Tool Calls**")
            if st.session_state.agent_results:
                latest_result = st.session_state.agent_results[-1]
                
                with st.container(height=450):
                    if latest_result.get('mcp_calls'):
                        for idx, mcp_call in enumerate(latest_result['mcp_calls']):
                            with st.expander(f"🔧 {mcp_call.get('tool', 'Unknown')} - {mcp_call.get('status', 'unknown')}"):
                                st.markdown(f"**Tool:** {mcp_call.get('tool', 'N/A')}")
                                st.markdown(f"**Status:** {mcp_call.get('status', 'N/A')}")
                                if mcp_call.get('output'):
                                    st.markdown("**Output:**")
                                    st.code(mcp_call['output'], language='text')
                    else:
                        st.info("No MCP calls in this response")
            else:
                st.info("No MCP calls yet")
        
        with tab3:
            st.markdown("**Citations & References**")
            if st.session_state.agent_results:
                latest_result = st.session_state.agent_results[-1]
                
                with st.container(height=450):
                    if latest_result.get('citations'):
                        for idx, citation in enumerate(latest_result['citations'], 1):
                            with st.expander(f"📚 Citation {idx}: {citation.get('text', 'N/A')}"):
                                st.markdown(f"**Source:** {citation.get('file_name', 'N/A')}")
                                if citation.get('quote'):
                                    st.markdown("**Quote:**")
                                    st.markdown(f"> {citation['quote']}")
                    else:
                        st.info("No citations in this response")
            else:
                st.info("No citations yet")
        
        with tab4:
            st.markdown("**Token Usage Statistics**")
            
            with st.container(height=450):
                # Current response usage
                if st.session_state.agent_results:
                    latest_result = st.session_state.agent_results[-1]
                    usage = latest_result.get('usage', {})
                    
                    st.markdown("#### Current Response")
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        st.metric("Prompt Tokens", usage.get('prompt_tokens', 0))
                    with col_b:
                        st.metric("Completion Tokens", usage.get('completion_tokens', 0))
                    with col_c:
                        st.metric("Total Tokens", usage.get('total_tokens', 0))
                
                st.markdown("---")
                
                # Total usage across session
                st.markdown("#### Session Total")
                col_d, col_e, col_f = st.columns(3)
                
                with col_d:
                    st.metric("Total Prompt", st.session_state.total_usage['prompt_tokens'])
                with col_e:
                    st.metric("Total Completion", st.session_state.total_usage['completion_tokens'])
                with col_f:
                    st.metric("Total Tokens", st.session_state.total_usage['total_tokens'])
                
                # Cost estimation (approximate using GPT-4 pricing)
                total_cost = (
                    st.session_state.total_usage['prompt_tokens'] * 0.00003 +
                    st.session_state.total_usage['completion_tokens'] * 0.00006
                )
                
                st.markdown("---")
                st.markdown(f"**Estimated Cost:** ${total_cost:.4f}")
                st.caption("*Based on approximate GPT-4 pricing")
        
        with tab5:
            st.markdown("**Video Generation from Skit**")
            
            with st.container(height=450):
                if st.session_state.agent_results and st.session_state.agent_results[-1].get('response_text'):
                    latest_response = st.session_state.agent_results[-1].get('response_text', '')
                    
                    # Show preview of what will be used
                    with st.expander("📋 Skit Content (for video)", expanded=False):
                        st.text_area(
                            "This content will be used for video generation:",
                            value=latest_response[:500] + "..." if len(latest_response) > 500 else latest_response,
                            height=100,
                            disabled=True,
                            key="skit_preview"
                        )
                    
                    st.markdown("---")
                    
                    # Generate video button
                    if not st.session_state.video_generating:
                        if st.button("🎬 Generate Video from Skit", type="primary", use_container_width=True):
                            st.session_state.video_generating = True
                            st.rerun()
                    
                    # Video generation progress
                    if st.session_state.video_generating:
                        with st.spinner("🎬 Generating video..."):
                            progress_bar = st.progress(0, text="Initializing video generation...")
                            status_text = st.empty()
                            
                            try:
                                # Update progress
                                progress_bar.progress(10, text="Sending request to Sora...")
                                status_text.info("📤 Creating video generation task...")
                                
                                # Create video (this will handle the polling internally)
                                video_path = createvideo(latest_response)
                                
                                progress_bar.progress(100, text="Video generation complete!")
                                status_text.success("✅ Video generated successfully!")
                                
                                st.session_state.generated_video = video_path
                                st.session_state.video_generating = False
                                
                                time.sleep(1)  # Brief pause to show completion
                                st.rerun()
                                
                            except Exception as e:
                                st.session_state.video_generating = False
                                status_text.error(f"❌ Error generating video: {str(e)}")
                                progress_bar.empty()
                    
                    # Display generated video
                    if st.session_state.generated_video:
                        st.markdown("---")
                        st.markdown("### 🎥 Generated Video")
                        
                        if os.path.exists(st.session_state.generated_video):
                            # Display video
                            video_file = open(st.session_state.generated_video, 'rb')
                            video_bytes = video_file.read()
                            st.video(video_bytes)
                            
                            # Download button
                            st.download_button(
                                label="📥 Download Video",
                                data=video_bytes,
                                file_name=os.path.basename(st.session_state.generated_video),
                                mime="video/mp4",
                                use_container_width=True
                            )
                            
                            # Clear video button
                            if st.button("🗑️ Clear Video", use_container_width=True):
                                st.session_state.generated_video = None
                                st.rerun()
                        else:
                            st.warning("⚠️ Video file not found. Please regenerate.")
                            if st.button("🔄 Clear and Retry"):
                                st.session_state.generated_video = None
                                st.rerun()
                else:
                    st.info("💡 Generate a skit first to create a video!")
                    st.markdown("""
                    **How to use:**
                    1. Enter a skit topic in the chat
                    2. Wait for the agent to generate the skit
                    3. Come back to this tab
                    4. Click 'Generate Video from Skit'
                    """)
    
    # Chat input at the bottom
    st.markdown("---")
    user_input = st.chat_input("Enter your skit topic or prompt here...")
    
    if user_input:
        # Add user message to chat history
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input
        })
        
        # Show processing status
        with st.spinner("🤖 Agent is thinking...", show_time=True):
            try:
                # Call the agent
                result = asyncio.run(existingagent(user_input))
                
                # Add agent response to chat history
                st.session_state.chat_history.append({
                    "role": "agent",
                    "content": result.get('response_text', 'No response generated')
                })
                
                # Store agent results
                st.session_state.agent_results.append(result)
                
                # Update total usage
                usage = result.get('usage', {})
                st.session_state.total_usage['prompt_tokens'] += usage.get('prompt_tokens', 0)
                st.session_state.total_usage['completion_tokens'] += usage.get('completion_tokens', 0)
                st.session_state.total_usage['total_tokens'] += usage.get('total_tokens', 0)
                
                st.success("✅ Response generated successfully!")
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ Error: {str(e)}")
                st.session_state.chat_history.append({
                    "role": "agent",
                    "content": f"Error occurred: {str(e)}"
                })
    
    # Clear conversation button in sidebar
    with st.sidebar:
        st.markdown("### 🎛️ Controls")
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.agent_results = []
            st.session_state.total_usage = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
            st.rerun()
        
        st.markdown("---")
        st.markdown("### ℹ️ About")
        st.markdown("""
        **STSKit** is a Streamlit-based AI agent toolkit for creating skits.
        
        Built with:
        - 🎨 Material Design 3
        - 🤖 Azure AI Agents
        - 📊 Real-time token tracking
        """)

if __name__ == "__main__":
    skitmain()