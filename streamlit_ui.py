# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
import json
from datetime import datetime
from random import randint
from typing import Annotated, Dict, List, Any
import requests
import streamlit as st

from agent_framework import ChatAgent, ChatMessage
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import get_tracer, setup_observability
from pydantic import Field

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Streamlit page
st.set_page_config(
    page_title="Azure AI Agent Chat",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state FIRST - before any other operations
def initialize_session_state():
    """Initialize all session state variables"""
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    if 'debug_logs' not in st.session_state:
        st.session_state.debug_logs = []
    
    if 'tool_calls' not in st.session_state:
        st.session_state.tool_calls = []
    
    if 'agent_created' not in st.session_state:
        st.session_state.agent_created = False
    
    if 'agent_id' not in st.session_state:
        st.session_state.agent_id = None
    
    if 'demo_mode' not in st.session_state:
        st.session_state.demo_mode = True
    
    if 'token_usage' not in st.session_state:
        st.session_state.token_usage = {
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'interactions': 0,
            'details': []  # per message usage breakdown
        }
    if 'ephemeral_agents' not in st.session_state:
        # When True, delete the Azure agent after every response (transaction)
        st.session_state.ephemeral_agents = False
    if 'force_tool_use' not in st.session_state:
        st.session_state.force_tool_use = False

# Initialize session state immediately
initialize_session_state()

# Custom CSS for better styling
st.markdown("""
<style>
    .main > div {
        padding-top: 1rem;
        padding-bottom: 2rem;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 0 24px;
        background-color: #f0f2f6;
        border-radius: 8px;
        margin-right: 8px;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background-color: #0066cc;
        color: white;
    }
    
    /* Chat message styling */
    .stChatMessage {
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0.75rem;
        background-color: #f8f9fa;
        border: 1px solid #e0e0e0;
    }
    
    /* Container styling */
    div[data-testid="stVerticalBlock"] > div[style*="height: 500px"] {
        border: 1px solid #d0d0d0;
        border-radius: 0.75rem;
        padding: 1rem;
        background-color: #ffffff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    div[data-testid="stVerticalBlock"] > div[style*="height: 450px"] {
        border: 1px solid #d0d0d0;
        border-radius: 0.75rem;
        padding: 1rem;
        background-color: #f8f9fa;
        font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
        font-size: 0.85rem;
    }
    
    /* Input styling */
    .stChatInput > div {
        border: 2px solid #0066cc;
        border-radius: 0.75rem;
        background-color: white;
    }
    
    /* Status indicators */
    .status-connected {
        background: linear-gradient(135deg, #56ab2f 0%, #a8e6cf 100%);
        padding: 0.5rem 1rem;
        border-radius: 0.5rem;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 0.5rem;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    try:
        # Step 1: Convert location -> lat/lon using Open-Meteo Geocoding
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        geo_response = requests.get(geo_url)

        if geo_response.status_code != 200:
            return f"Failed to get coordinates. Status code: {geo_response.status_code}"

        geo_data = geo_response.json()
        if "results" not in geo_data or len(geo_data["results"]) == 0:
            return f"Could not find location: {location}"

        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]

        # Step 2: Get weather for that lat/lon
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            current_weather = data.get("current_weather", {})
            temperature = current_weather.get("temperature")
            windspeed = current_weather.get("windspeed")
            return f"Weather in {location}: {temperature}°C, Wind speed: {windspeed} km/h"
        else:
            return f"Failed to get weather data. Status code: {response.status_code}"

    except Exception as e:
        import traceback
        return f"Error fetching weather data: {str(e)}\n{traceback.format_exc()}"

async def create_agent():
    """Create the Azure AI agent"""
    try:
        # Check if environment variables are set
        endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        
        if not endpoint or not model:
            log_debug("Missing Azure environment variables - cannot create agent")
            log_debug(f"AZURE_AI_PROJECT_ENDPOINT: {'SET' if endpoint else 'NOT SET'}")
            log_debug(f"AZURE_AI_MODEL_DEPLOYMENT_NAME: {'SET' if model else 'NOT SET'}")
            st.error("Missing required environment variables: AZURE_AI_PROJECT_ENDPOINT and/or AZURE_AI_MODEL_DEPLOYMENT_NAME")
            return False
        
        log_debug("Creating Azure AI agent...")
        log_debug(f"Endpoint: {endpoint}")
        log_debug(f"Model: {model}")
        
        try:
            log_debug("Initializing Azure CLI credential...")
            credential = AzureCliCredential()
            # credential = DefaultAzureCredential()
            
            log_debug("Creating AI Project client...")
            client = AIProjectClient(
                endpoint=endpoint, 
                credential=credential,
                # api_key=api_key
            )

            # await client.setup_azure_ai_observability()
            
            log_debug("Creating agent...")
            # Create an agent that will persist for the session
            created_agent = await client.agents.create_agent(
                model=model, 
                name=f"StreamlitWeatherAgent_{randint(1000, 9999)}"
            )
            
            st.session_state.agent_id = created_agent.id
            st.session_state.agent_created = True
            st.session_state.client = client
            st.session_state.credential = credential
            st.session_state.demo_mode = False
            
            log_debug(f"Agent successfully created with ID: {created_agent.id}")
            return True
            
        except Exception as inner_e:
            log_debug(f"Inner creation error: {str(inner_e)}")
            log_debug(f"Error type: {type(inner_e).__name__}")
            raise inner_e
        
    except Exception as e:
        error_msg = f"Failed to create agent: {str(e)}"
        log_debug(error_msg)
        log_debug(f"Exception type: {type(e).__name__}")
        st.error(error_msg)
        return False

async def create_agent_with_data(session_data: dict = None):
    """Create the Azure AI agent and return session data"""
    try:
        # Check if environment variables are set
        endpoint = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
        model = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        
        if not endpoint or not model:
            print(f"[DEBUG] Missing Azure environment variables - cannot create agent")
            print(f"[DEBUG] AZURE_AI_PROJECT_ENDPOINT: {'SET' if endpoint else 'NOT SET'}")
            print(f"[DEBUG] AZURE_AI_MODEL_DEPLOYMENT_NAME: {'SET' if model else 'NOT SET'}")
            return False, {}
        
        print(f"[DEBUG] Creating Azure AI agent...")
        print(f"[DEBUG] Endpoint: {endpoint}")
        print(f"[DEBUG] Model: {model}")
        
        try:
            print(f"[DEBUG] Initializing Azure CLI credential...")
            credential = AzureCliCredential()
            
            # credential = DefaultAzureCredential()
            
            print(f"[DEBUG] Creating AI Project client...")
            client = AIProjectClient(
                endpoint=endpoint, 
                credential=credential,
                # api_key=api_key
            )
            #await client.setup_azure_ai_observability()

            # async with AzureAIAgentClient(project_client=client) as agentclient:
            #     # This will enable tracing and configure the application to send telemetry data to the
            #     # Application Insights instance attached to the Azure AI project.
            #     # This will override any existing configuration.
            #     await agentclient.setup_azure_ai_observability()

            
            print(f"[DEBUG] Creating agent...")
            # Create an agent that will persist for the session
            created_agent = await client.agents.create_agent(
                model=model, 
                # name=f"StreamlitWeatherAgent_{randint(1000, 9999)}"
                name="StreamlitWeatherAgent_1"
            )
            
            # Return session data
            new_session_data = {
                'agent_id': created_agent.id,
                'agent_created': True,
                'client': client,
                'credential': credential,
                'demo_mode': False
            }
            
            # Also update Streamlit session state if available
            try:
                st.session_state.agent_id = created_agent.id
                st.session_state.agent_created = True
                st.session_state.client = client
                st.session_state.credential = credential
                st.session_state.demo_mode = False
            except:
                # Session state not available in thread context
                pass
            
            print(f"[DEBUG] Agent successfully created with ID: {created_agent.id}")
            return True, new_session_data
            
        except Exception as inner_e:
            print(f"[DEBUG] Inner creation error: {str(inner_e)}")
            print(f"[DEBUG] Error type: {type(inner_e).__name__}")
            raise inner_e
        
    except Exception as e:
        error_msg = f"Failed to create agent: {str(e)}"
        print(f"[DEBUG] {error_msg}")
        print(f"[DEBUG] Exception type: {type(e).__name__}")
        return False, {}
    
# Per-call captured tool events (to be merged back in main thread)
tool_events = []

def instrumented_get_weather(location: str) -> str:
    start_ts = datetime.now().strftime('%H:%M:%S')
    output = get_weather(location)
    tool_events.append({
        'timestamp': start_ts,
        'tool': 'get_weather',
        'input': location,
        'output': output,
        'source': 'local'
    })
    tlog(f"Tool get_weather executed for '{location}'")
    return output
# Add Microsoft Learn MCP tool
mcplearn = HostedMCPTool(
        name="Microsoft Learn MCP",
        url="https://learn.microsoft.com/api/mcp",
        approval_mode='never_require'
    )

hfmcp = HostedMCPTool(
        name="HuggingFace MCP",
        url="https://huggingface.co/mcp",
        # approval_mode='always_require'  # for testing approval flow
        approval_mode='never_require'
    )

thread_logs = []  # collect logs to merge later in main thread

def tlog(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    thread_logs.append(f"[{timestamp}] {msg}")

def normalize_text(obj) -> str:
    """Best-effort extraction of human-readable text from various response object shapes."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    # Common agent framework patterns
    for attr in ("output", "content", "text", "message"):
        if hasattr(obj, attr):
            try:
                v = getattr(obj, attr)
                if isinstance(v, (str, bytes)):
                    return v.decode() if isinstance(v, bytes) else v
                # If it's a list of messages
                if isinstance(v, list):
                    # Join string-like entries
                    collected = []
                    for item in v:
                        if isinstance(item, str):
                            collected.append(item)
                        elif isinstance(item, dict) and 'content' in item:
                            collected.append(str(item['content']))
                        else:
                            collected.append(str(item))
                    return "\n".join(collected)
            except Exception:
                pass
    # Dict / list fallback
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)
    # Fallback to str
    return str(obj)

def safe_token_count(text_like) -> int:
    text = normalize_text(text_like)
    if not text:
        return 0
    return int(len(text.split()) * 1.3)

async def process_agent(message, client, ephemeral, session_data, agent_id, agent_created):
    """Process a message through the agent and return the response."""
    async with ChatAgent(
        chat_client=AzureAIAgentClient(
            project_client=client, 
            agent_id=agent_id
        ),
        instructions=(
            "You are a helpful AI agent. Always call the 'get_weather' tool to obtain current "
            "conditions whenever the user asks about weather, temperature, forecast, climate or related info. "
            "If the user prompt is not about weather you may answer normally. "
            "If a force tool flag is set (developer toggle), you must call the tool at least once before answering. "
            "After calling the tool, craft a friendly answer that cites the tool result."
            "If the users asks for microsoft or azure learning resources, use the Microsoft Learn MCP tool."
            "if the user asks for HuggingFace related resources, use the HuggingFace MCP tool."
            "provide details and also links to the resources from the MCP tool."
        ),
        tools=[instrumented_get_weather, mcplearn, hfmcp],
        temperature=0.0,
        max_tokens=2500,
    ) as agent:
        
        tlog("Agent initialized, processing request...")
        # result_obj = await agent.run(message)
        created_thread = await client.agents.threads.create()
        thread = agent.get_new_thread(service_thread_id=created_thread.id)

        result_obj = await agent.run(message, thread=thread)
        tlog("Agent response received")
        result = normalize_text(result_obj)

        # Try to extract token usage metadata from agent / underlying response if available
        usage = None
        try:
            # Common patterns: agent.last_response.usage or agent._last_response
            possible = getattr(agent, 'last_response', None) or getattr(agent, '_last_response', None)
            if possible and isinstance(possible, dict):
                usage_obj = possible.get('usage') or possible.get('token_usage')
                if usage_obj:
                    usage = {
                        'prompt_tokens': usage_obj.get('prompt_tokens') or usage_obj.get('input_tokens'),
                        'completion_tokens': usage_obj.get('completion_tokens') or usage_obj.get('output_tokens'),
                        'total_tokens': usage_obj.get('total_tokens') or (
                            (usage_obj.get('prompt_tokens') or usage_obj.get('input_tokens') or 0) +
                            (usage_obj.get('completion_tokens') or usage_obj.get('output_tokens') or 0)
                        )
                    }
        except Exception as meta_e:
            tlog(f"Token usage metadata extraction failed: {meta_e}")
        
        # ---- MCP TOOL CALL EXTRACTION (primary success path) ----
        def extract_mcp_tool_calls(raw_obj):
            calls = []
            if not raw_obj:
                return calls
            try:
                # Accept dict-like or object with attributes
                candidate = raw_obj
                if hasattr(raw_obj, 'model_dump'):
                    candidate = raw_obj.model_dump()
                if not isinstance(candidate, (dict, list)):
                    return calls
                # Normalize to list of messages if fits OpenAI / function-calling pattern
                container = []
                if isinstance(candidate, dict):
                    # Look for 'choices' style
                    if 'choices' in candidate and isinstance(candidate['choices'], list):
                        container = candidate['choices']
                    else:
                        container = [candidate]
                else:
                    container = candidate
                for entry in container:
                    # OpenAI style: entry['message']['tool_calls']
                    msg = entry.get('message') if isinstance(entry, dict) else None
                    if isinstance(msg, dict) and 'tool_calls' in msg:
                        for tc in msg['tool_calls']:
                            name = tc.get('function', {}).get('name') or tc.get('name') or 'unknown_function'
                            args = tc.get('function', {}).get('arguments') or tc.get('arguments') or {}
                            calls.append({
                                'timestamp': datetime.now().strftime('%H:%M:%S'),
                                'tool': name,
                                'input': args if isinstance(args, str) else json.dumps(args, ensure_ascii=False),
                                'output': '(result not directly exposed)',
                                'source': 'mcp'
                            })
                    # Azure / generic pattern: entry.get('toolInvocations')
                    if isinstance(entry, dict) and 'toolInvocations' in entry and isinstance(entry['toolInvocations'], list):
                        for inv in entry['toolInvocations']:
                            name = inv.get('name') or inv.get('toolName') or 'unknown_tool'
                            args = inv.get('input') or inv.get('arguments') or {}
                            out = inv.get('output') or inv.get('result') or '(no output field)'
                            calls.append({
                                'timestamp': datetime.now().strftime('%H:%M:%S'),
                                'tool': name,
                                'input': args if isinstance(args, str) else json.dumps(args, ensure_ascii=False),
                                'output': out if isinstance(out, str) else json.dumps(out, ensure_ascii=False),
                                'source': 'mcp'
                            })
                return calls
            except Exception as mcp_e:
                tlog(f"MCP extraction error: {mcp_e}")
                return calls

        # Attempt extraction from multiple possible objects
        mcp_sources = []
        try:
            possible_last = getattr(agent, 'last_response', None) or getattr(agent, '_last_response', None)
            if possible_last:
                mcp_sources.append(possible_last)
            mcp_sources.append(result_obj)
        except Exception:
            pass
        for src_obj in mcp_sources:
            for mcpcall in extract_mcp_tool_calls(src_obj):
                # Avoid duplicates by (tool,input,source) triple
                signature = (mcpcall['tool'], mcpcall['input'], mcpcall['source'])
                if not any((e['tool'], e['input'], e.get('source','local')) == signature for e in tool_events):
                    tool_events.append(mcpcall)

        if usage is None:
            # Fallback heuristic
            prompt_tokens = safe_token_count(message)
            completion_tokens = safe_token_count(result)
            usage = {
                'prompt_tokens': prompt_tokens,
                'completion_tokens': completion_tokens,
                'total_tokens': prompt_tokens + completion_tokens
            }
            tlog("Using heuristic token counts (library did not expose usage)")

        # Synthetic fallback tool event if none occurred (clarity in UI)
        if not tool_events:
            tool_events.append({
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'tool': 'NO_TOOL_INVOKED',
                'input': '(n/a)',
                'output': 'Model responded without invoking any registered or MCP tool.',
                'source': 'synthetic'
            })

        # Optionally delete agent after response (ephemeral transaction)
        if ephemeral and agent_id:
            try:
                tlog(f"Ephemeral mode enabled - deleting agent {agent_id}")
                await client.agents.delete_agent(agent_id)
                await client.agents.threads.delete(created_thread.id)
                if session_data is not None:
                    session_data['agent_created'] = False
                    session_data['agent_id'] = None
                agent_created = False
                agent_id = None
                tlog("Agent deleted successfully after transaction")
            except Exception as del_e:
                tlog(f"Agent deletion failed: {del_e}")

        return {
            'response': result,
            'logs': thread_logs,
            'usage': usage,
            'tools': tool_events,
            'agent_created': agent_created,
            'agent_id': agent_id
        }

async def send_message(message: str, session_data: dict = None):
    """Send a message to the agent and get response.

    NOTE: This function is executed inside a worker thread (via send_message_wrapper).
    It SHOULD NOT directly mutate st.session_state (Streamlit is not thread-safe).
    Instead, it returns the response text and a list of debug log lines plus token usage info.
    """
    try:


        # Use session_data if provided (from thread), otherwise use session_state
        if session_data:
            agent_created = session_data.get('agent_created', False)
            agent_id = session_data.get('agent_id', None)
            client = session_data.get('client', None)
            credential = session_data.get('credential', None)
        else:
            agent_created = st.session_state.get('agent_created', False)
            agent_id = st.session_state.get('agent_id', None)
            client = st.session_state.get('client', None)
            credential = st.session_state.get('credential', None)
        
        ephemeral = None
        try:
            # Read ephemeral preference (thread-safe fallback to False)
            ephemeral = (session_data and session_data.get('ephemeral_agents')) or (
                hasattr(st, 'session_state') and st.session_state.get('ephemeral_agents', False)
            )
        except Exception:
            ephemeral = False

        # Determine whether to force tool usage
        force_tool = False
        try:
            force_tool = (session_data and session_data.get('force_tool_use')) or (
                hasattr(st, 'session_state') and st.session_state.get('force_tool_use', False)
            )
        except Exception:
            force_tool = False

        # Ensure we have a valid, existing agent – otherwise create one
        if not (agent_created and agent_id and client):
            tlog("No active agent found – creating a new agent instance")
            success, new_session_data = await create_agent_with_data(session_data)
            if not success:
                return {
                    'response': "Failed to initialize agent. Please check your Azure configuration.",
                    'logs': thread_logs,
                    'usage': None,
                    'tools': [],
                    'agent_created': False,
                    'agent_id': None
                }
            # Update session data with new values
            if session_data:
                session_data.update(new_session_data)
            agent_created = new_session_data.get('agent_created', False)
            agent_id = new_session_data.get('agent_id', None)
            client = new_session_data.get('client', None)
            tlog(f"Agent created with ID {agent_id}")
        else:
            tlog(f"Reusing existing agent {agent_id}")
        
        tlog(f"Sending message: {message}")

        
        # Use the actual Azure AI Agent Framework
        try:
            with get_tracer().start_as_current_span("Single Agent framework1", kind=SpanKind.CLIENT) as current_span:
                print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
                rs = process_agent(message, client, ephemeral, session_data, agent_id, agent_created)

            result = await rs     
            return result           
                
        except Exception as agent_error:
            tlog(f"Agent error: {str(agent_error)}")
            # If there's an agent error, try to recreate the agent
            tlog("Attempting to recreate agent due to error...")
            success, new_session_data = await create_agent_with_data(session_data)
            if success:
                # Update session data
                if session_data:
                    session_data.update(new_session_data)
                client = new_session_data.get('client', None)
                agent_id = new_session_data.get('agent_id', None)

                with get_tracer().start_as_current_span("Single Agent framework-excep", kind=SpanKind.CLIENT) as current_span:
                    print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
                
                    rs = process_agent(message, client, ephemeral, session_data, agent_id, agent_created)

                result = await rs
                return result
            else:
                return {
                    'response': f"Failed to recreate agent after error: {str(agent_error)}",
                    'logs': thread_logs,
                    'usage': None,
                    'tools': tool_events,
                    'agent_created': agent_created,
                    'agent_id': agent_id
                }
            
    except Exception as e:
        error_msg = f"Error processing message: {str(e)}"
        thread_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {error_msg}")
        return {
            'response': f"Sorry, I encountered an error: {str(e)}",
            'logs': thread_logs,
            'usage': None,
            'tools': [],
            'agent_created': False,
            'agent_id': None
        }

def send_message_wrapper(message: str):
    """Wrapper to handle async send_message in Streamlit"""
    import threading
    import concurrent.futures
    
    # Capture current session state values before threading
    session_data = {
         'agent_created': st.session_state.get('agent_created', False),
         'agent_id': st.session_state.get('agent_id', None),
         'client': st.session_state.get('client', None),
         'credential': st.session_state.get('credential', None),
         'demo_mode': st.session_state.get('demo_mode', True),
         'ephemeral_agents': st.session_state.get('ephemeral_agents', False),
         'force_tool_use': st.session_state.get('force_tool_use', False)
     }
    
    def run_async_in_thread():
        """Run async function in a new thread with its own event loop"""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Run the async function with session data
                result_dict = loop.run_until_complete(send_message(message, session_data))
                return result_dict
            finally:
                # Clean up the loop
                loop.close()
                
        except Exception as e:
            error_msg = f"Thread execution error: {str(e)}"
            # Can't use log_debug here as we're in a different thread
            print(f"[DEBUG] {error_msg}")
            return {'response': error_msg, 'logs': [error_msg], 'usage': None}
    
    try:
        # Execute in a separate thread to avoid event loop conflicts
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_async_in_thread)
            result = future.result(timeout=60)  # 60 second timeout
            
            # Update session state with any changes that occurred in the thread
            # This ensures agent creation persists back to the main thread
            # Always sync back agent lifecycle (handles both creation & deletion)
            if isinstance(result, dict):
                # Update session_data snapshot with new states from result
                if 'agent_created' in result:
                    session_data['agent_created'] = result['agent_created']
                if 'agent_id' in result:
                    session_data['agent_id'] = result['agent_id']

            st.session_state.agent_created = session_data.get('agent_created', False)
            st.session_state.agent_id = session_data.get('agent_id', None)
            st.session_state.client = session_data.get('client', None)
            st.session_state.credential = session_data.get('credential', None)
            st.session_state.demo_mode = session_data.get('demo_mode', True)

            if st.session_state.agent_created:
                log_debug(f"Agent active: {st.session_state.agent_id}")
            else:
                log_debug("No active agent (ephemeral deletion or not yet created)")
            # Merge thread logs into debug logs
            if isinstance(result, dict) and result.get('logs'):
                for line in result['logs']:
                    # Avoid duplicating lines already added (simple containment check)
                    if line not in st.session_state.debug_logs:
                        st.session_state.debug_logs.append(line)

            # Merge tool events
            if isinstance(result, dict) and result.get('tools'):
                if 'tool_calls' not in st.session_state:
                    st.session_state.tool_calls = []
                for ev in result['tools']:
                    st.session_state.tool_calls.append(ev)

            # Update token usage
            if isinstance(result, dict) and result.get('usage'):
                u = result['usage']
                st.session_state.token_usage['prompt_tokens'] += u.get('prompt_tokens', 0)
                st.session_state.token_usage['completion_tokens'] += u.get('completion_tokens', 0)
                st.session_state.token_usage['total_tokens'] += u.get('total_tokens', 0)
                st.session_state.token_usage['interactions'] += 1
                st.session_state.token_usage['details'].append({
                    'timestamp': datetime.now().strftime('%H:%M:%S'),
                    'prompt_tokens': u.get('prompt_tokens', 0),
                    'completion_tokens': u.get('completion_tokens', 0),
                    'total_tokens': u.get('total_tokens', 0)
                })

            return result.get('response') if isinstance(result, dict) else result
            
    except concurrent.futures.TimeoutError:
        error_msg = "Request timed out after 60 seconds"
        log_debug(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error in message wrapper: {str(e)}"
        log_debug(error_msg)
        return error_msg

def log_debug(message: str):
    """Add a debug log entry"""
    # Ensure session state is initialized
    if 'debug_logs' not in st.session_state:
        st.session_state.debug_logs = []
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.debug_logs.append(f"[{timestamp}] {message}")

def display_chat_messages():
    """Display chat messages in the chat container"""
    if not st.session_state.messages:
        st.markdown("### Welcome! 👋")
        st.markdown("Ask me about the weather in any city around the world!")
        st.markdown("*Example: 'What's the weather like in Tokyo?'*")
    else:
        for message in st.session_state.messages:
            with st.chat_message(message["role"], avatar="🧑‍💼" if message["role"] == "user" else "🤖"):
                st.markdown(message["content"])

def display_debug_logs():
    """Display debug logs"""
    if st.session_state.debug_logs:
        # Show last 50 logs
        recent_logs = st.session_state.debug_logs[-50:]
        for log in recent_logs:
            st.text(log)
    else:
        st.info("🔍 Debug logs will appear here when you start chatting")

def display_tool_calls():
    """Display tool call history"""
    if st.session_state.tool_calls:
        # Show last 20 calls
        recent_calls = st.session_state.tool_calls[-20:]
        for i, call in enumerate(recent_calls):
            source = call.get('source', 'local')
            if call['tool'] == 'NO_TOOL_INVOKED':
                icon = "🛈"
            elif source == 'mcp':
                icon = "🧩"
            elif source == 'synthetic':
                icon = "ℹ️"
            else:
                icon = "🔧"
            with st.expander(f"{icon} {call['tool']} - {call['timestamp']}", expanded=(i == len(recent_calls)-1)):
                 st.write(f"**Tool:** {call['tool']}")
                 st.write(f"**Input:** {call['input']}")
                 st.write(f"**Output:** {call['output']}")
                 st.write(f"**Source:** {source}")
                 if source == 'mcp':
                    st.caption("🔗 Extracted from MCP / function-calling metadata.")
                 elif call['tool'] == 'NO_TOOL_INVOKED':
                    st.caption("ℹ️ No tool calls detected (synthetic).")
    else:
        st.info("🛠️ Tool calls will appear here when the agent uses tools (a synthetic entry will note when none were used).")

def display_token_usage():
    """Display token usage statistics"""
    usage = st.session_state.get('token_usage', {})
    if not usage:
        st.info("No token usage yet")
        return
    cols = st.columns(4)
    cols[0].metric("Prompt Tokens", usage.get('prompt_tokens', 0))
    cols[1].metric("Completion Tokens", usage.get('completion_tokens', 0))
    cols[2].metric("Total Tokens", usage.get('total_tokens', 0))
    cols[3].metric("Interactions", usage.get('interactions', 0))
    if usage.get('details'):
        with st.expander("Detailed Usage (last 10)", expanded=False):
            for row in usage['details'][-10:]:
                st.write(f"{row['timestamp']}: prompt={row['prompt_tokens']} completion={row['completion_tokens']} total={row['total_tokens']}")

def cleanup_agent():
    """Clean up the agent when session ends"""
    try:
        if st.session_state.agent_created and st.session_state.agent_id:
            log_debug(f"Agent {st.session_state.agent_id} session ended")
            st.session_state.agent_created = False
            st.session_state.agent_id = None
    except Exception as e:
        log_debug(f"Error cleaning up agent: {str(e)}")

def main():
    # Ensure session state is initialized first
    initialize_session_state()
    
    st.title("🤖 Azure AI Agent Chat Interface")
    
    # Check environment variables
    required_env_vars = ["AZURE_AI_PROJECT_ENDPOINT", "AZURE_AI_MODEL_DEPLOYMENT_NAME"]
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    
    if missing_vars:
        st.error(f"Missing environment variables: {', '.join(missing_vars)}")
        st.info("Please set up your .env file with the required Azure AI project settings.")
        log_debug(f"Missing environment variables: {', '.join(missing_vars)}")
        return
    
    # Create two columns for the main layout
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("💬 Chat")
        
        # Chat container with fixed height and scrolling
        with st.container(height=500):
            display_chat_messages()
    
    with col2:
        st.subheader("🔧 Debug, Tools & Usage")
        
        # Create tabs for debug, tools, and token usage
        debug_tab, tools_tab, usage_tab = st.tabs(["Debug Output", "Tool Calls", "Token Usage"])
        
        with debug_tab:
            with st.container(height=450):
                display_debug_logs()
        
        with tools_tab:
            with st.container(height=450):
                display_tool_calls()
        
        with usage_tab:
            with st.container(height=450):
                display_token_usage()
    
    # Fixed chat input at the bottom
    st.markdown("---")
    
    # Chat input
    if prompt := st.chat_input("Ask me about the weather in any location..."):
        # Add user message to chat history
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Get assistant response
        with st.spinner("Processing your request...", show_time=True):
            response = send_message_wrapper(prompt)
            
            if response:
                # Add assistant response to chat history
                st.session_state.messages.append({"role": "assistant", "content": response})
            else:
                error_msg = "Sorry, I encountered an error processing your request."
                st.session_state.messages.append({"role": "assistant", "content": error_msg})
        
        # Rerun to update the display
        st.rerun()
    
    # Sidebar with controls
    with st.sidebar:
        st.header("Controls")
        
        if st.button("Clear Chat History"):
            st.session_state.messages = []
            st.rerun()
        
        if st.button("Clear Debug Logs"):
            st.session_state.debug_logs = []
            st.rerun()
        
        if st.button("Clear Tool Calls"):
            st.session_state.tool_calls = []
            st.rerun()
        # Ephemeral agent toggle
        st.toggle(
            "Ephemeral Agent (delete after each response)",
            key="ephemeral_agents",
            help="When enabled, the Azure Agent is created for each message and deleted immediately after the response."
        )
        st.toggle(
            "Force Weather Tool",
            key="force_tool_use",
            help="Force at least one weather tool invocation before responding."
        )
        
        st.header("Status")
        if st.session_state.agent_created:
            if st.session_state.get('demo_mode', True):
                st.success("✅ Demo Agent Active")
                st.info("💡 Using simulated weather agent")
            else:
                st.success("✅ Azure AI Agent Connected")
                st.write(f"Agent ID: `{st.session_state.agent_id}`")
        else:
            st.info("🔄 Agent will be created on first message")
        
        st.header("Statistics")
        st.metric("Messages", len(st.session_state.messages))
        st.metric("Debug Logs", len(st.session_state.debug_logs))
        st.metric("Tool Calls", len(st.session_state.tool_calls))

async def cleanup_agent():
    """Clean up the agent when session ends"""
    try:
        if st.session_state.agent_created and st.session_state.agent_id and not st.session_state.get('demo_mode', True):
            client = st.session_state.client
            await client.agents.delete_agent(st.session_state.agent_id)
            log_debug(f"Agent {st.session_state.agent_id} cleaned up")
    except Exception as e:
        log_debug(f"Error cleaning up agent: {str(e)}")

if __name__ == "__main__":
    setup_observability()
    main()