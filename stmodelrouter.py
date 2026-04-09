# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import html as html_lib
import json
import logging
import os
import re
import time as _time
import traceback
from typing import cast

import streamlit as st
import streamlit.components.v1 as components
from openai import AzureOpenAI
from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Message,
    WorkflowEvent,
)
from agent_framework.orchestrations import GroupChatRequestSentEvent, MagenticBuilder, MagenticProgressLedger
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.ai.projects import AIProjectClient
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

myEndpoint = os.getenv("AZURE_AI_PROJECT")


def _extract_response_metadata(resp, turn, existing_metadata):
    """Extract model, usage, and other properties from a completed response."""
    meta = dict(existing_metadata)
    model = getattr(resp, 'model', None)
    if model:
        meta['Model'] = model
    meta['Response ID'] = resp.id
    meta['Status'] = getattr(resp, 'status', 'unknown')
    created = getattr(resp, 'created_at', None)
    if created:
        meta['Created At'] = datetime.fromtimestamp(created).strftime('%Y-%m-%d %H:%M:%S')
    completed = getattr(resp, 'completed_at', None)
    if completed:
        meta['Completed At'] = datetime.fromtimestamp(completed).strftime('%Y-%m-%d %H:%M:%S')
        if created:
            meta['Duration (s)'] = round(completed - created, 2)
    usage = getattr(resp, 'usage', None)
    if usage:
        meta['Input Tokens'] = getattr(usage, 'input_tokens', None)
        cached = getattr(getattr(usage, 'input_tokens_details', None), 'cached_tokens', None)
        if cached is not None:
            meta['Cached Input Tokens'] = cached
        meta['Output Tokens'] = getattr(usage, 'output_tokens', None)
        reasoning = getattr(getattr(usage, 'output_tokens_details', None), 'reasoning_tokens', None)
        if reasoning is not None:
            meta['Reasoning Tokens'] = reasoning
        meta['Total Tokens'] = getattr(usage, 'total_tokens', None)
    for attr, label in [
        ('temperature', 'Temperature'),
        ('top_p', 'Top P'),
        ('frequency_penalty', 'Frequency Penalty'),
        ('presence_penalty', 'Presence Penalty'),
        ('max_output_tokens', 'Max Output Tokens'),
        ('service_tier', 'Service Tier'),
        ('truncation', 'Truncation'),
    ]:
        val = getattr(resp, attr, None)
        if val is not None:
            meta[label] = val
    reasoning_obj = getattr(resp, 'reasoning', None)
    if reasoning_obj:
        effort = getattr(reasoning_obj, 'effort', None)
        if effort:
            meta['Reasoning Effort'] = effort
    agent_ref = getattr(resp, 'agent_reference', None)
    if agent_ref and isinstance(agent_ref, dict):
        meta['Agent Name'] = agent_ref.get('name', '')
        meta['Agent Version'] = agent_ref.get('version', '')
    meta['Turn'] = turn
    return meta


def _extract_sources(output_str, sources_list):
    """Extract knowledge base source titles from MCP call output."""
    if not output_str or not isinstance(output_str, str):
        return
    from urllib.parse import unquote
    for match in re.finditer(r'"title"\s*:\s*"([^"]+)"', output_str):
        title = match.group(1).encode().decode('unicode_escape', errors='replace')
        sources_list.append(title)
    if not sources_list:
        for match in re.finditer(r'"chunk_id"\s*:\s*"[^_]+_([A-Za-z0-9+/=]+)_pages_', output_str):
            try:
                decoded = base64.b64decode(match.group(1) + '==').decode('utf-8', errors='replace').strip()
                if '/' in decoded:
                    filename = unquote(decoded.rsplit('/', 1)[-1])
                else:
                    filename = decoded
                if filename:
                    sources_list.append(filename)
            except Exception:
                pass


def run_agent_query(query):
    """Run a query against the model router agent, returning structured results."""
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )
    my_agent = "modelrouteragent"
    my_version = "6"
    openai_client = project_client.get_openai_client()

    agent_ref = {"agent_reference": {"name": my_agent, "version": my_version, "type": "agent_reference"}}
    previous_response_id = None
    max_turns = 10
    full_text = ""
    sources = []
    response_metadata = {}

    def _process_stream(stream, turn, label=""):
        nonlocal full_text, sources, response_metadata
        approval_requests = []
        response_id = None
        got_text = False
        for event in stream:
            event_type = getattr(event, 'type', None)
            if event_type == 'response.output_text.delta':
                full_text += event.delta
                got_text = True
            elif event_type == 'response.output_item.done':
                item = event.item
                if getattr(item, 'type', None) == 'mcp_approval_request':
                    approval_requests.append(item)
                elif getattr(item, 'type', None) == 'mcp_call':
                    output = getattr(item, 'output', None)
                    _extract_sources(output, sources)
            elif event_type == 'response.completed':
                resp = event.response
                response_id = resp.id
                response_metadata = _extract_response_metadata(resp, turn, response_metadata)
        return approval_requests, response_id, got_text

    for turn in range(max_turns):
        create_kwargs = dict(extra_body=agent_ref, stream=True)
        if previous_response_id:
            create_kwargs["input"] = []
            create_kwargs["previous_response_id"] = previous_response_id
        else:
            create_kwargs["input"] = [{"role": "user", "content": query}]

        stream = openai_client.responses.create(**create_kwargs)
        approval_requests, response_id, got_text = _process_stream(stream, turn)

        if approval_requests and not got_text:
            previous_response_id = response_id
            approve_input = [{"type": "mcp_approval_response", "approve": True, "approval_request_id": req.id} for req in approval_requests]
            stream = openai_client.responses.create(
                input=approve_input,
                previous_response_id=previous_response_id,
                extra_body=agent_ref,
                stream=True,
            )
            _, response_id, got_text = _process_stream(stream, turn, "cont")
            if got_text:
                break
            previous_response_id = response_id
        else:
            break

    unique_sources = list(dict.fromkeys(sources))
    return {
        "text": full_text,
        "sources": unique_sources,
        "metadata": response_metadata,
    }


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="Model Router Agent",
        page_icon="🔀",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Material Design 3 inspired CSS
    st.markdown("""
    <style>
    /* ---- MD3 color tokens ---- */
    :root {
        --md-primary: #1a73e8;
        --md-on-primary: #ffffff;
        --md-surface: #f8f9fa;
        --md-surface-container: #ffffff;
        --md-surface-container-high: #f1f3f4;
        --md-on-surface: #1f1f1f;
        --md-on-surface-variant: #5f6368;
        --md-outline: #dadce0;
        --md-outline-variant: #e8eaed;
        --md-secondary: #e8f0fe;
        --md-tertiary: #fce8e6;
        --md-tertiary-text: #c5221f;
        --md-success: #e6f4ea;
        --md-success-text: #137333;
    }

    /* Remove default Streamlit padding & scrolling */
    .stMainBlockContainer { padding-top: 1rem !important; padding-bottom: 0 !important; }
    header[data-testid="stHeader"] { display: none !important; }
    footer { display: none !important; }
    html, body, [data-testid="stAppViewContainer"] { overflow: hidden !important; }

    /* Title bar */
    .md3-title-bar {
        background: var(--md-primary);
        color: var(--md-on-primary);
        padding: 12px 24px;
        border-radius: 16px;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    }
    .md3-title-bar h1 { margin: 0; font-size: 1.25rem; font-weight: 500; letter-spacing: 0.01em; }
    .md3-title-bar .subtitle { font-size: 0.8rem; opacity: 0.85; margin-top: 2px; }

    /* Card container */
    .md3-card {
        background: var(--md-surface-container);
        border: 1px solid var(--md-outline);
        border-radius: 16px;
        padding: 0;
        overflow: hidden;
        box-shadow: 0 1px 2px rgba(0,0,0,0.06);
    }
    .md3-card-header {
        background: var(--md-surface-container-high);
        padding: 10px 16px;
        border-bottom: 1px solid var(--md-outline-variant);
        font-weight: 500;
        font-size: 0.85rem;
        color: var(--md-on-surface);
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .md3-card-body { padding: 12px 16px; }

    /* Chat bubbles */
    .chat-user {
        background: var(--md-secondary);
        color: var(--md-primary);
        padding: 10px 14px;
        border-radius: 12px 12px 4px 12px;
        margin: 6px 0;
        font-size: 0.88rem;
        max-width: 95%;
        margin-left: auto;
        text-align: right;
    }
    .chat-assistant {
        background: var(--md-surface-container-high);
        color: var(--md-on-surface);
        padding: 10px 14px;
        border-radius: 12px 12px 12px 4px;
        margin: 6px 0;
        font-size: 0.88rem;
        max-width: 95%;
        line-height: 1.55;
    }

    /* Metric chips */
    .md3-chip {
        display: inline-flex;
        align-items: center;
        gap: 4px;
        background: var(--md-surface-container-high);
        border: 1px solid var(--md-outline);
        border-radius: 8px;
        padding: 4px 10px;
        font-size: 0.78rem;
        color: var(--md-on-surface-variant);
        margin: 2px 3px;
    }
    .md3-chip .chip-label { font-weight: 500; color: var(--md-on-surface); }

    /* Source pill */
    .md3-source-pill {
        display: inline-block;
        background: var(--md-success);
        color: var(--md-success-text);
        border-radius: 8px;
        padding: 4px 10px;
        font-size: 0.78rem;
        margin: 2px 3px;
        font-weight: 500;
    }

    /* Status badge */
    .md3-badge-success {
        display: inline-block;
        background: var(--md-success);
        color: var(--md-success-text);
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 0.72rem;
        font-weight: 500;
    }
    .md3-badge-info {
        display: inline-block;
        background: var(--md-secondary);
        color: var(--md-primary);
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 0.72rem;
        font-weight: 500;
    }

    /* Property table */
    .md3-prop-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
    .md3-prop-table td { padding: 5px 8px; border-bottom: 1px solid var(--md-outline-variant); }
    .md3-prop-table td:first-child { color: var(--md-on-surface-variant); font-weight: 500; width: 45%; }
    .md3-prop-table td:last-child { color: var(--md-on-surface); }

    /* Expander tweaks */
    [data-testid="stExpander"] { border: 1px solid var(--md-outline) !important; border-radius: 12px !important; }

    /* Scrollable containers */
    [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlockBorderWrapper"] > div > div {
        scrollbar-width: thin;
        scrollbar-color: var(--md-outline) transparent;
    }

    /* Chat input */
    [data-testid="stChatInput"] { border-top: 1px solid var(--md-outline-variant); }
    </style>
    """, unsafe_allow_html=True)

    # ---- Session State ----
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_outputs" not in st.session_state:
        st.session_state.agent_outputs = []

    # ---- Title Bar ----
    st.markdown("""
    <div class="md3-title-bar">
        <div>
            <h1>🔀 Model Router Agent</h1>
            <div class="subtitle">Azure AI Foundry &middot; Knowledge-grounded RFP Agent</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Two-column layout ----
    col_left, col_right = st.columns([1, 1], gap="medium")

    # ---- LEFT: Conversation History ----
    with col_left:
        st.markdown("""<div class="md3-card"><div class="md3-card-header">💬 Conversation History</div></div>""", unsafe_allow_html=True)
        chat_container = st.container(height=500)
        with chat_container:
            if not st.session_state.messages:
                st.markdown(
                    '<p style="text-align:center;color:var(--md-on-surface-variant);padding:60px 20px;font-size:0.9rem;">'
                    'Ask a question to get started.</p>',
                    unsafe_allow_html=True,
                )
            for msg in st.session_state.messages:
                if msg["role"] == "user":
                    st.markdown(f'<div class="chat-user">{msg["content"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="chat-assistant">{msg["content"]}</div>', unsafe_allow_html=True)

    # ---- RIGHT: Agent Output & Metadata ----
    with col_right:
        st.markdown("""<div class="md3-card"><div class="md3-card-header">🤖 Agent Response Details</div></div>""", unsafe_allow_html=True)
        detail_container = st.container(height=500)
        with detail_container:
            if not st.session_state.agent_outputs:
                st.markdown(
                    '<p style="text-align:center;color:var(--md-on-surface-variant);padding:60px 20px;font-size:0.9rem;">'
                    'Agent details will appear here after a query.</p>',
                    unsafe_allow_html=True,
                )
            for output in st.session_state.agent_outputs:
                meta = output.get("metadata", {})
                sources = output.get("sources", [])

                # Model & status header
                model_name = meta.get("Model", "Unknown")
                status = meta.get("Status", "unknown")
                duration = meta.get("Duration (s)", "—")
                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<span class="md3-badge-info">{model_name}</span> '
                    f'<span class="md3-badge-success">{status}</span> '
                    f'<span class="md3-chip"><span class="chip-label">⏱ {duration}s</span></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Token usage chips
                input_tok = meta.get("Input Tokens", 0)
                output_tok = meta.get("Output Tokens", 0)
                total_tok = meta.get("Total Tokens", 0)
                cached_tok = meta.get("Cached Input Tokens", 0)
                reasoning_tok = meta.get("Reasoning Tokens", 0)
                st.markdown(
                    f'<div style="margin-bottom:8px;">'
                    f'<span class="md3-chip">📥 Input <span class="chip-label">{input_tok}</span></span>'
                    f'<span class="md3-chip">📤 Output <span class="chip-label">{output_tok}</span></span>'
                    f'<span class="md3-chip">📊 Total <span class="chip-label">{total_tok}</span></span>'
                    f'<span class="md3-chip">💾 Cached <span class="chip-label">{cached_tok}</span></span>'
                    f'<span class="md3-chip">🧠 Reasoning <span class="chip-label">{reasoning_tok}</span></span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Knowledge Base Sources
                if sources:
                    st.markdown(
                        '<div style="font-weight:500;font-size:0.82rem;margin:6px 0 4px;color:var(--md-on-surface);">📚 Knowledge Base Sources</div>',
                        unsafe_allow_html=True,
                    )
                    pills_html = "".join(f'<span class="md3-source-pill">{src}</span>' for src in sources)
                    st.markdown(f'<div style="margin-bottom:8px;">{pills_html}</div>', unsafe_allow_html=True)

                # Response properties expander
                with st.expander("📋 Full Response Properties", expanded=False):
                    # Split into parameter groups
                    model_params = {}
                    token_params = {}
                    agent_params = {}
                    other_params = {}
                    token_keys = {'Input Tokens', 'Output Tokens', 'Total Tokens', 'Cached Input Tokens', 'Reasoning Tokens'}
                    model_keys = {'Model', 'Temperature', 'Top P', 'Frequency Penalty', 'Presence Penalty',
                                  'Max Output Tokens', 'Reasoning Effort', 'Truncation', 'Service Tier'}
                    agent_keys = {'Agent Name', 'Agent Version', 'Turn'}

                    for k, v in meta.items():
                        if k in token_keys:
                            token_params[k] = v
                        elif k in model_keys:
                            model_params[k] = v
                        elif k in agent_keys:
                            agent_params[k] = v
                        else:
                            other_params[k] = v

                    def _render_table(params, title):
                        if not params:
                            return
                        rows = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in params.items())
                        st.markdown(
                            f'<div style="font-weight:500;font-size:0.8rem;margin:6px 0 2px;color:var(--md-primary);">{title}</div>'
                            f'<table class="md3-prop-table">{rows}</table>',
                            unsafe_allow_html=True,
                        )

                    _render_table(model_params, "Model Parameters")
                    _render_table(token_params, "Token Usage")
                    _render_table(agent_params, "Agent Info")
                    _render_table(other_params, "Response Info")

                st.markdown('<hr style="border:none;border-top:1px solid var(--md-outline-variant);margin:10px 0;">', unsafe_allow_html=True)

    # ---- Chat Input (pinned at bottom) ----
    if prompt := st.chat_input("Ask the Model Router Agent a question..."):
        # Append user message
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Run agent
        with st.spinner("Agent is processing...", show_time=True):
            result = run_agent_query(prompt)

        # Append assistant message
        st.session_state.messages.append({"role": "assistant", "content": result["text"]})
        st.session_state.agent_outputs.append(result)
        st.rerun()


if __name__ == "__main__":
    main()