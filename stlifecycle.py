import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Annotated, Dict, List, Any
import requests
import streamlit as st
from utils import get_weather, fetch_stock_data
import io
import sys
import time

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

# Material Design 3 Color Palette
MD3_PRIMARY = "#6750A4"
MD3_SECONDARY = "#625B71"
MD3_TERTIARY = "#7D5260"
MD3_SUCCESS = "#006D3B"
MD3_ERROR = "#BA1A1A"
MD3_WARNING = "#7D5700"
MD3_SURFACE = "#FFFBFE"
MD3_SURFACE_VARIANT = "#E7E0EC"
MD3_ON_SURFACE = "#1C1B1F"

# Configure Streamlit page
st.set_page_config(
    page_title="AI Agent Lifecycle Management",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Material Design 3
def load_custom_css():
    st.markdown("""
    <style>
        /* Material Design 3 Custom Styles */
        .main {
            background-color: #FFFBFE;
        }
        
        .stButton>button {
            background-color: #6750A4;
            color: white;
            border: none;
            border-radius: 20px;
            padding: 12px 24px;
            font-weight: 500;
            font-size: 14px;
            letter-spacing: 0.1px;
            transition: all 0.3s ease;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        }
        
        .stButton>button:hover {
            background-color: #7965B3;
            box-shadow: 0 3px 6px rgba(0,0,0,0.16), 0 3px 6px rgba(0,0,0,0.23);
            transform: translateY(-1px);
        }
        
        .stButton>button:active {
            transform: translateY(0);
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
        }
        
        .card {
            background-color: #FFFFFF;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24);
            margin-bottom: 16px;
        }
        
        .card-header {
            font-size: 22px;
            font-weight: 500;
            color: #1C1B1F;
            margin-bottom: 12px;
        }
        
        .card-description {
            font-size: 14px;
            color: #49454F;
            line-height: 20px;
            margin-bottom: 16px;
        }
        
        .status-chip {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 500;
            margin-right: 8px;
        }
        
        .status-success {
            background-color: #D4F4E2;
            color: #006D3B;
        }
        
        .status-running {
            background-color: #FFF4E5;
            color: #7D5700;
        }
        
        .status-error {
            background-color: #FFDAD6;
            color: #BA1A1A;
        }
        
        .metric-card {
            background: linear-gradient(135deg, #6750A4 0%, #7965B3 100%);
            border-radius: 16px;
            padding: 20px;
            color: white;
            box-shadow: 0 4px 6px rgba(103,80,164,0.3);
        }
        
        .metric-value {
            font-size: 32px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .metric-label {
            font-size: 14px;
            opacity: 0.9;
        }
        
        h1 {
            color: #1C1B1F;
            font-weight: 500;
            letter-spacing: 0;
        }
        
        h2, h3 {
            color: #1C1B1F;
            font-weight: 500;
        }
        
        .stExpander {
            background-color: #FFFFFF;
            border-radius: 12px;
            border: 1px solid #E7E0EC;
            margin-bottom: 8px;
        }
        
        .sidebar .sidebar-content {
            background-color: #F5F2F7;
        }
        
        .info-banner {
            background-color: #E8DEF8;
            color: #1C1B1F;
            padding: 16px;
            border-radius: 12px;
            border-left: 4px solid #6750A4;
            margin-bottom: 24px;
        }
    </style>
    """, unsafe_allow_html=True)

def create_header():
    """Create the main header with title and description"""
    st.markdown("""
        <div style='text-align: center; padding: 20px 0;'>
            <h1 style='font-size: 42px; margin-bottom: 8px;'>🤖 AI Agent Lifecycle Management</h1>
            <p style='font-size: 16px; color: #49454F;'>
                Manage and monitor your AI agents through their complete lifecycle
            </p>
        </div>
    """, unsafe_allow_html=True)

def create_sidebar():
    """Create sidebar with information and settings"""
    with st.sidebar:
        st.markdown("### 📋 Agent Operations")
        st.markdown("""
        This dashboard provides comprehensive management capabilities for AI agents:
        
        **🚀 Existing Agent**  
        Run and test existing agent configurations
        
        **📊 Agent Evaluation**  
        Evaluate agent performance and quality metrics
        
        **🛡️ Red Team Testing**  
        Security and safety assessment through adversarial testing
        """)
        
        st.markdown("---")
        st.markdown("### ⚙️ Configuration")
        
        # Check environment variables
        env_status = {
            "AZURE_AI_PROJECT_ENDPOINT": os.environ.get("AZURE_AI_PROJECT_ENDPOINT", ""),
            "AZURE_AI_AGENT_NAME": os.environ.get("AZURE_AI_AGENT_NAME", "rfpagent"),
            "AZURE_AI_MODEL_DEPLOYMENT_NAME": os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "")
        }
        
        for key, value in env_status.items():
            status = "✅" if value else "❌"
            st.markdown(f"{status} `{key}`")
        
        st.markdown("---")
        st.markdown("### 📚 Documentation")
        st.markdown("[Azure AI Projects](https://learn.microsoft.com/azure/ai-services/)")

def capture_output(func):
    """Capture stdout and stderr from function execution"""
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()
    
    start_time = time.time()
    success = False
    error_msg = None
    
    try:
        func()
        success = True
    except Exception as e:
        success = False
        error_msg = str(e)
    finally:
        stdout_value = sys.stdout.getvalue()
        stderr_value = sys.stderr.getvalue()
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    return {
        "success": success,
        "stdout": stdout_value,
        "stderr": stderr_value,
        "error": error_msg,
        "elapsed_time": elapsed_time,
        "start_time": start_time,
        "end_time": end_time
    }

def display_results(result, operation_name):
    """Display execution results in an expandable container"""
    if result["success"]:
        st.success(f"✅ {operation_name} completed successfully in {result['elapsed_time']:.2f} seconds")
    else:
        st.error(f"❌ {operation_name} failed after {result['elapsed_time']:.2f} seconds")
    
    # Create expandable containers for output
    col1, col2 = st.columns(2)
    
    with col1:
        with st.expander("📝 Standard Output", expanded=result["success"]):
            if result["stdout"]:
                st.code(result["stdout"], language="text")
            else:
                st.info("No output generated")
    
    with col2:
        with st.expander("⚠️ Errors & Warnings", expanded=not result["success"]):
            if result["stderr"]:
                st.code(result["stderr"], language="text")
            elif result["error"]:
                st.code(result["error"], language="text")
            else:
                st.info("No errors or warnings")
    
    # Execution details
    with st.expander("⏱️ Execution Details"):
        details_col1, details_col2, details_col3 = st.columns(3)
        with details_col1:
            st.metric("Duration", f"{result['elapsed_time']:.2f}s")
        with details_col2:
            st.metric("Start Time", datetime.fromtimestamp(result['start_time']).strftime('%H:%M:%S'))
        with details_col3:
            st.metric("End Time", datetime.fromtimestamp(result['end_time']).strftime('%H:%M:%S'))

def st_lifecycle():
    """Main Streamlit lifecycle function"""
    load_custom_css()
    create_header()
    create_sidebar()
    
   
    # Main content area with tabs
    tab1, tab2, tab3 = st.tabs(["🚀 Existing Agent", "📊 Agent Evaluation", "🛡️ Red Team Testing"])
    
    # Tab 1: Existing Agent
    with tab1:
        with st.container(height=500):
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-header'>Existing Agent Execution</div>", unsafe_allow_html=True)
            st.markdown("""
                <div class='card-description'>
                    Execute and interact with your existing agent configuration. This operation will 
                    initialize the agent, process requests, and display responses in real-time.
                </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([3, 1], gap="medium")
            with col1:
                st.markdown("**Features:**")
                st.markdown("- Real-time agent response monitoring")
                st.markdown("- Conversation history tracking")
                st.markdown("- Performance metrics collection")
            
            with col2:
                if st.button("▶️ Run Agent", key="btn_existing_agent", use_container_width=True):
                    with st.spinner("Executing agent...", show_time=True):
                        result = capture_output(existingagent)
                        st.session_state['existing_agent_result'] = result
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Display results if available
            if 'existing_agent_result' in st.session_state:
                st.markdown("### Results")
                display_results(st.session_state['existing_agent_result'], "Existing Agent")
    
    # Tab 2: Agent Evaluation
    with tab2:
        with st.container(height=500):
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-header'>Agent Evaluation</div>", unsafe_allow_html=True)
            st.markdown("""
                <div class='card-description'>
                    Perform comprehensive evaluation of your agent's performance, including accuracy, 
                    relevance, coherence, and other quality metrics.
                </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([3, 1], gap="medium")
            with col1:
                st.markdown("**Evaluation Metrics:**")
                st.markdown("- Response quality and relevance")
                st.markdown("- Task completion accuracy")
                st.markdown("- Groundedness and coherence")
                st.markdown("- Performance benchmarking")
            
            with col2:
                if st.button("📊 Start Evaluation", key="btn_agent_eval", use_container_width=True):
                    with st.spinner("Running evaluation...", show_time=True):
                        result = capture_output(agenteval)
                        st.session_state['agent_eval_result'] = result
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Display results if available
            if 'agent_eval_result' in st.session_state:
                st.markdown("### Evaluation Results")
                display_results(st.session_state['agent_eval_result'], "Agent Evaluation")
        
    # Tab 3: Red Team Testing
    with tab3:
        with st.container(height=500):
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown("<div class='card-header'>Red Team Security Testing</div>", unsafe_allow_html=True)
            st.markdown("""
                <div class='card-description'>
                    Execute adversarial testing to identify potential security vulnerabilities, safety issues, 
                    and areas where the agent might produce harmful or inappropriate responses.
                </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([3, 1], gap="medium")
            with col1:
                st.markdown("**Security Checks:**")
                st.markdown("- Prohibited actions detection")
                st.markdown("- Sensitive data leakage prevention")
                st.markdown("- Harmful content filtering")
                st.markdown("- Adversarial attack resistance")
            
            with col2:
                if st.button("🛡️ Run Red Team", key="btn_redteam", use_container_width=True):
                    with st.spinner("Running red team tests...", show_time=True):
                        result = capture_output(redteam_main)
                        st.session_state['redteam_result'] = result
            
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Display results if available
            if 'redteam_result' in st.session_state:
                st.markdown("### Security Test Results")
                display_results(st.session_state['redteam_result'], "Red Team Testing")
        
    # Summary metrics at the bottom
    st.markdown("---")
    st.markdown("### 📈 Execution Summary")
    
    col1, col2, col3 = st.columns(3, gap="medium")
    
    with col1:
        if 'existing_agent_result' in st.session_state:
            status = "✅ Completed" if st.session_state['existing_agent_result']['success'] else "❌ Failed"
            elapsed = st.session_state['existing_agent_result']['elapsed_time']
            st.markdown(f"""
                <div class='metric-card'>
                    <div class='metric-label'>Existing Agent</div>
                    <div class='metric-value'>{status}</div>
                    <div class='metric-label'>{elapsed:.2f} seconds</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class='metric-card'>
                    <div class='metric-label'>Existing Agent</div>
                    <div class='metric-value'>Not Run</div>
                    <div class='metric-label'>-</div>
                </div>
            """, unsafe_allow_html=True)
    
    with col2:
        if 'agent_eval_result' in st.session_state:
            status = "✅ Completed" if st.session_state['agent_eval_result']['success'] else "❌ Failed"
            elapsed = st.session_state['agent_eval_result']['elapsed_time']
            st.markdown(f"""
                <div class='metric-card'>
                    <div class='metric-label'>Agent Evaluation</div>
                    <div class='metric-value'>{status}</div>
                    <div class='metric-label'>{elapsed:.2f} seconds</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class='metric-card'>
                    <div class='metric-label'>Agent Evaluation</div>
                    <div class='metric-value'>Not Run</div>
                    <div class='metric-label'>-</div>
                </div>
            """, unsafe_allow_html=True)
    
    with col3:
        if 'redteam_result' in st.session_state:
            status = "✅ Completed" if st.session_state['redteam_result']['success'] else "❌ Failed"
            elapsed = st.session_state['redteam_result']['elapsed_time']
            st.markdown(f"""
                <div class='metric-card'>
                    <div class='metric-label'>Red Team Testing</div>
                    <div class='metric-value'>{status}</div>
                    <div class='metric-label'>{elapsed:.2f} seconds</div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
                <div class='metric-card'>
                    <div class='metric-label'>Red Team Testing</div>
                    <div class='metric-value'>Not Run</div>
                    <div class='metric-label'>-</div>
                </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    st_lifecycle()
