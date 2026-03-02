import asyncio
import logging
import streamlit as st
from pathlib import Path
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import ResponseStreamEventType
import os
from dotenv import load_dotenv
from datetime import datetime
import time

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

myEndpoint = os.getenv("AZURE_AI_PROJECT")

# ─────────────────────────────────────────────────────────────────────────────
# Material Design 3 – Indigo / Deep-Purple Professional Theme
# ─────────────────────────────────────────────────────────────────────────────

MD3_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Global resets ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* ── Hide default Streamlit chrome ── */
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display: none;}

/* ── MD3 Surface tokens ── */
:root {
    --md-sys-color-primary: #283593;
    --md-sys-color-on-primary: #FFFFFF;
    --md-sys-color-primary-container: #C5CAE9;
    --md-sys-color-surface: #FAFAFE;
    --md-sys-color-surface-container: #FFFFFF;
    --md-sys-color-surface-container-high: #E8EAF6;
    --md-sys-color-on-surface: #1C1B1F;
    --md-sys-color-on-surface-variant: #49454F;
    --md-sys-color-outline: #C5CAE9;
    --md-sys-color-outline-variant: #E8EAF6;
    --md-sys-color-secondary: #3949AB;
    --md-sys-color-tertiary: #5C6BC0;
    --md-sys-color-error: #B3261E;
    --md-sys-color-shadow: rgba(0,0,0,0.08);
}

/* ── Top App Bar ── */
.md3-top-bar {
    background: linear-gradient(135deg, #1A237E 0%, #283593 40%, #3949AB 100%);
    color: white;
    padding: 20px 32px;
    border-radius: 0 0 28px 28px;
    margin: -1rem -1rem 1.5rem -1rem;
    box-shadow: 0 4px 16px rgba(26, 35, 126, 0.3);
}
.md3-top-bar h1 {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 600;
    letter-spacing: -0.02em;
}
.md3-top-bar p {
    margin: 4px 0 0 0;
    font-size: 0.85rem;
    opacity: 0.85;
    font-weight: 300;
}

/* ── MD3 Elevated Card ── */
.md3-card {
    background: var(--md-sys-color-surface-container);
    border: 1px solid var(--md-sys-color-outline);
    border-radius: 16px;
    box-shadow: 0 1px 3px var(--md-sys-color-shadow), 0 4px 12px var(--md-sys-color-shadow);
    transition: box-shadow 0.2s ease;
}
.md3-card:hover {
    box-shadow: 0 2px 6px var(--md-sys-color-shadow), 0 8px 24px var(--md-sys-color-shadow);
}

/* ── Section labels ── */
.md3-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--md-sys-color-secondary);
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* ── Chat bubbles ── */
.chat-bubble-user {
    background: linear-gradient(135deg, #283593, #3949AB);
    color: white;
    padding: 14px 20px;
    border-radius: 20px 20px 6px 20px;
    margin: 8px 0;
    max-width: 85%;
    margin-left: auto;
    font-size: 0.92rem;
    line-height: 1.55;
    box-shadow: 0 2px 8px rgba(40, 53, 147, 0.25);
    word-wrap: break-word;
}
.chat-bubble-assistant {
    background: var(--md-sys-color-surface-container-high);
    color: var(--md-sys-color-on-surface);
    padding: 14px 20px;
    border-radius: 20px 20px 20px 6px;
    margin: 8px 0;
    max-width: 85%;
    font-size: 0.92rem;
    line-height: 1.55;
    border: 1px solid var(--md-sys-color-outline);
    word-wrap: break-word;
}

/* ── Token chip ── */
.md3-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--md-sys-color-surface-container-high);
    border: 1px solid var(--md-sys-color-outline);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--md-sys-color-on-surface);
}

/* ── Metric cards ── */
.metric-row {
    display: flex;
    gap: 12px;
    margin: 12px 0;
    flex-wrap: wrap;
}
.metric-tile {
    flex: 1;
    min-width: 100px;
    background: var(--md-sys-color-surface-container-high);
    border-radius: 16px;
    padding: 16px;
    text-align: center;
    border: 1px solid var(--md-sys-color-outline);
}
.metric-tile .value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--md-sys-color-primary);
}
.metric-tile .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--md-sys-color-on-surface-variant);
    margin-top: 4px;
}

/* ── Streamlit overrides for MD3 feel ── */
.stChatInput > div {
    border-radius: 28px !important;
    border: 2px solid var(--md-sys-color-outline) !important;
    box-shadow: 0 2px 8px var(--md-sys-color-shadow) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.stChatInput > div:focus-within {
    border-color: var(--md-sys-color-primary) !important;
    box-shadow: 0 2px 12px rgba(40, 53, 147, 0.18) !important;
}

.stExpander {
    border: 1px solid var(--md-sys-color-outline) !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 4px var(--md-sys-color-shadow) !important;
    margin-bottom: 8px !important;
}

div[data-testid="stVerticalBlock"] > div:has(> div.stExpander) {
    gap: 0.5rem;
}

/* ── Scrollable container tweaks ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    border-color: var(--md-sys-color-outline) !important;
}

/* ── Timestamp ── */
.chat-timestamp {
    font-size: 0.65rem;
    color: var(--md-sys-color-on-surface-variant);
    margin-top: 2px;
    opacity: 0.7;
}

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: var(--md-sys-color-on-surface-variant);
}
.empty-state .icon { font-size: 3rem; margin-bottom: 12px; }
.empty-state h3 { margin: 0; font-weight: 500; color: var(--md-sys-color-on-surface); }
.empty-state p { font-size: 0.85rem; margin-top: 6px; }
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Agent interaction – returns structured data for the UI
# ─────────────────────────────────────────────────────────────────────────────

def studentiq(query: str) -> dict:
    """
    Calls the StudentIQ agent workflow and returns:
      {
        "final_text": str,
        "agent_outputs": [ {"name": str, "status": str, "text": str}, ... ],
        "token_usage": {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int},
        "events_raw": [str, ...],
        "elapsed_seconds": float,
      }
    """
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )

    result = {
        "final_text": "",
        "agent_outputs": [],
        "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "events_raw": [],
        "debug_events": [],   # full debug dump of every event
        "elapsed_seconds": 0,
    }

    current_agent = {"name": "Orchestrator", "text": "", "status": "running"}
    all_text_chunks = []  # fallback: collect ALL text we see
    start_time = time.time()

    def _dump_event(evt):
        """Return a debug-friendly dict of every attribute on the event."""
        info = {"type": str(getattr(evt, 'type', '??'))}
        for attr in ['text', 'delta', 'content', 'data', 'output', 'message',
                     'item', 'response', 'part', 'name', 'role',
                     'action_id', 'status', 'previous_action_id']:
            val = getattr(evt, attr, None)
            if val is not None:
                try:
                    # Nested objects: try to grab their dict
                    if hasattr(val, '__dict__'):
                        nested = {}
                        for k, v in vars(val).items():
                            try:
                                nested[k] = str(v)[:200]
                            except Exception:
                                nested[k] = '<unserializable>'
                        info[attr] = nested
                    else:
                        info[attr] = str(val)[:300]
                except Exception:
                    info[attr] = '<error reading>'
        return info

    def _extract_text(evt):
        """Pull text from whichever attribute the event carries."""
        for attr in ['text', 'delta', 'content', 'data', 'output', 'message']:
            val = getattr(evt, attr, None)
            if val and isinstance(val, str):
                return val
        return None

    with project_client:
        workflow = {
            "name": "StudentIQ",
            "version": "1",
        }

        openai_client = project_client.get_openai_client()
        conversation = openai_client.conversations.create()

        stream = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent": {"name": workflow["name"], "type": "agent_reference"}},
            input=query,
            stream=True,
            metadata={"x-ms-debug-mode-enabled": "1"},
        )

        for event in stream:
            # ── Always dump full debug ──
            debug_entry = _dump_event(event)
            result["debug_events"].append(debug_entry)

            evt_type = str(getattr(event, 'type', ''))

            # ── TEXT_DONE ──
            if event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DONE:
                txt = _extract_text(event) or ""
                result["final_text"] += txt + "\n"
                current_agent["text"] += txt + "\n"
                all_text_chunks.append(txt)
                result["events_raw"].append(f"TEXT_DONE: {txt[:120]}")

            # ── Workflow action ADDED (agent boundary) ──
            elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_ADDED and hasattr(event, 'item') and getattr(event.item, 'type', '') == "workflow_action":
                if current_agent["text"].strip():
                    current_agent["status"] = "done"
                    result["agent_outputs"].append(dict(current_agent))
                agent_name = getattr(event.item, 'action_id', None) or getattr(event.item, 'name', None) or "Agent"
                current_agent = {"name": agent_name, "text": "", "status": "running"}
                result["events_raw"].append(f"AGENT_START: {agent_name}")

            # ── Workflow action DONE ──
            elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_ITEM_DONE and hasattr(event, 'item') and getattr(event.item, 'type', '') == "workflow_action":
                status = getattr(event.item, 'status', 'done')
                current_agent["status"] = status
                result["events_raw"].append(f"AGENT_DONE: {current_agent['name']} → {status}")

            # ── TEXT_DELTA (streaming chunks) ──
            elif event.type == ResponseStreamEventType.RESPONSE_OUTPUT_TEXT_DELTA:
                txt = _extract_text(event) or ""
                current_agent["text"] += txt
                all_text_chunks.append(txt)
                result["events_raw"].append(f"DELTA: {txt[:80]}")

            # ── COMPLETED ──
            elif event.type == ResponseStreamEventType.RESPONSE_COMPLETED:
                if hasattr(event, "response") and hasattr(event.response, "usage"):
                    usage = event.response.usage
                    result["token_usage"] = {
                        "prompt_tokens": getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0,
                        "completion_tokens": getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0,
                        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
                    }
                result["events_raw"].append("RESPONSE_COMPLETED")

            # ── Catch-all: try to extract text anyway ──
            else:
                txt = _extract_text(event)
                if txt:
                    current_agent["text"] += txt + "\n"
                    all_text_chunks.append(txt)
                    result["events_raw"].append(f"CAPTURED({evt_type}): {txt[:80]}")
                else:
                    result["events_raw"].append(f"UNHANDLED: {evt_type}")

        # Flush final agent
        if current_agent["text"].strip():
            current_agent["status"] = "done"
            result["agent_outputs"].append(dict(current_agent))

        # Fallback: if final_text is empty but we collected text chunks, join them
        if not result["final_text"].strip() and all_text_chunks:
            result["final_text"] = "".join(all_text_chunks)

        openai_client.conversations.delete(conversation_id=conversation.id)

    result["elapsed_seconds"] = round(time.time() - start_time, 2)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit App
# ─────────────────────────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="StudentIQ",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Inject MD3 CSS
    st.markdown(MD3_CSS, unsafe_allow_html=True)

    # ── Top App Bar ──
    st.markdown("""
    <div class="md3-top-bar">
        <h1>🎓 StudentIQ</h1>
        <p>Your Intelligent Student Advisor — Powered by Microsoft Foundry Agents</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Session state init ──
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_outputs" not in st.session_state:
        st.session_state.agent_outputs = []
    if "token_usage" not in st.session_state:
        st.session_state.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if "total_queries" not in st.session_state:
        st.session_state.total_queries = 0
    if "elapsed_seconds" not in st.session_state:
        st.session_state.elapsed_seconds = 0
    if "debug_events" not in st.session_state:
        st.session_state.debug_events = []
    if "events_raw" not in st.session_state:
        st.session_state.events_raw = []

    # ── Two-column layout (wide gap) ──
    col_chat, col_gap, col_info = st.columns([5, 0.3, 3])

    # ════════════════════════════════════════════════════════════════════════
    # LEFT COLUMN — Chat Conversation
    # ════════════════════════════════════════════════════════════════════════
    with col_chat:
        st.markdown('<div class="md3-label">💬 CONVERSATION</div>', unsafe_allow_html=True)
        chat_container = st.container(height=500, border=True)

        with chat_container:
            if not st.session_state.messages:
                st.markdown("""
                <div class="empty-state">
                    <div class="icon">🎓</div>
                    <h3>Welcome to StudentIQ</h3>
                    <p>Ask any student-related, academic, or learning question below to get started.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                for msg in st.session_state.messages:
                    ts = msg.get("timestamp", "")
                    if msg["role"] == "user":
                        st.markdown(
                            f'<div class="chat-bubble-user">{msg["content"]}</div>'
                            f'<div class="chat-timestamp" style="text-align:right;">{ts}</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            f'<div class="chat-bubble-assistant">{msg["content"]}</div>'
                            f'<div class="chat-timestamp">{ts}</div>',
                            unsafe_allow_html=True,
                        )

    # ════════════════════════════════════════════════════════════════════════
    # RIGHT COLUMN — Token Usage & Agent Outputs
    # ════════════════════════════════════════════════════════════════════════
    with col_info:
        st.markdown('<div class="md3-label">📊 INSIGHTS & AGENT ACTIVITY</div>', unsafe_allow_html=True)
        info_container = st.container(height=500, border=True)

        with info_container:
            # ── Token usage metrics ──
            st.markdown("##### 🪙 Token Usage")
            tk = st.session_state.token_usage
            st.markdown(f"""
            <div class="metric-row">
                <div class="metric-tile">
                    <div class="value">{tk['prompt_tokens']:,}</div>
                    <div class="label">Prompt</div>
                </div>
                <div class="metric-tile">
                    <div class="value">{tk['completion_tokens']:,}</div>
                    <div class="label">Completion</div>
                </div>
                <div class="metric-tile">
                    <div class="value">{tk['total_tokens']:,}</div>
                    <div class="label">Total</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Session stats chips ──
            st.markdown(
                f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 16px 0;">'
                f'<span class="md3-chip">🔄 Queries: {st.session_state.total_queries}</span>'
                f'<span class="md3-chip">⏱️ Last: {st.session_state.elapsed_seconds}s</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            st.divider()

            # ── Individual agent outputs ──
            st.markdown("##### 🤖 Agent Outputs")
            if not st.session_state.agent_outputs:
                st.caption("Agent activity will appear here after your first query.")
            else:
                for i, agent in enumerate(st.session_state.agent_outputs):
                    status_icon = "🟢" if agent["status"] == "done" else "🟡"
                    with st.expander(f"{status_icon} {agent['name']}", expanded=(i == len(st.session_state.agent_outputs) - 1)):
                        st.markdown(agent["text"])

            st.divider()

            # ── Debug: Raw event log ──
            st.markdown("##### 🐛 Debug Log")
            if st.session_state.events_raw:
                with st.expander(f"📋 Event Stream ({len(st.session_state.events_raw)} events)", expanded=False):
                    for idx, evt_str in enumerate(st.session_state.events_raw):
                        st.text(f"{idx+1:>3}. {evt_str}")
            else:
                st.caption("No events captured yet.")

            if st.session_state.debug_events:
                with st.expander(f"🔬 Full Event Dump ({len(st.session_state.debug_events)} events)", expanded=False):
                    import json
                    for idx, dbg in enumerate(st.session_state.debug_events):
                        st.code(json.dumps(dbg, indent=2, default=str), language="json")

    # ── Gap column (visual spacer) ──
    with col_gap:
        st.empty()

    # ════════════════════════════════════════════════════════════════════════
    # Chat Input (pinned at bottom)
    # ════════════════════════════════════════════════════════════════════════
    user_input = st.chat_input("Ask StudentIQ anything…")

    if user_input:
        now = datetime.now().strftime("%I:%M %p")

        # Append user message
        st.session_state.messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": now,
        })

        # Call the agent
        with st.spinner("🎓 StudentIQ is thinking…", show_time=True):
            result = studentiq(user_input)

        # Append assistant message
        st.session_state.messages.append({
            "role": "assistant",
            "content": result["final_text"],
            "timestamp": datetime.now().strftime("%I:%M %p"),
        })

        # Update right-panel state
        st.session_state.agent_outputs = result["agent_outputs"]
        st.session_state.token_usage = result["token_usage"]
        st.session_state.total_queries += 1
        st.session_state.elapsed_seconds = result["elapsed_seconds"]
        st.session_state.debug_events = result.get("debug_events", [])
        st.session_state.events_raw = result.get("events_raw", [])

        st.rerun()


if __name__ == "__main__":
    main()