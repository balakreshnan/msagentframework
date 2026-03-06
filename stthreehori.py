import logging
import streamlit as st
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
import os
from dotenv import load_dotenv
from datetime import datetime
import time

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
        /* MD3 Color Palette – Deep Teal / Warm Surface */
        :root {
            --md-primary: #006A6A;
            --md-on-primary: #FFFFFF;
            --md-primary-container: #6FF7F6;
            --md-on-primary-container: #002020;
            --md-secondary: #4A6363;
            --md-on-secondary: #FFFFFF;
            --md-secondary-container: #CCE8E7;
            --md-tertiary: #4B607C;
            --md-tertiary-container: #D3E4FF;
            --md-surface: #F5FAFA;
            --md-surface-variant: #DAE5E4;
            --md-on-surface: #161D1D;
            --md-on-surface-variant: #3F4948;
            --md-outline: #6F7979;
            --md-outline-variant: #BEC9C8;
            --md-error: #BA1A1A;
            --md-success: #006D3B;
            --md-warning: #7C5800;
            --md-inverse-surface: #2B3232;
            --md-inverse-on-surface: #ECF2F1;
        }

        /* App background */
        .stApp {
            background: linear-gradient(160deg, var(--md-surface) 0%, #EDF3F3 50%, var(--md-surface-variant) 100%);
        }

        /* Hide default Streamlit chrome */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {background: transparent;}

        /* ---- Top Bar ---- */
        .horizon-topbar {
            background: linear-gradient(135deg, var(--md-primary) 0%, #008585 100%);
            color: var(--md-on-primary);
            padding: 20px 28px;
            border-radius: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 16px rgba(0,106,106,.25);
            display: flex;
            align-items: center;
            gap: 14px;
        }
        .horizon-topbar h1 {
            margin: 0; font-size: 26px; font-weight: 700; letter-spacing: -.3px;
        }
        .horizon-topbar p {
            margin: 2px 0 0; font-size: 13px; opacity: .85;
        }

        /* ---- Column headers ---- */
        .col-header {
            font-size: 15px;
            font-weight: 600;
            color: var(--md-primary);
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;
        }
        .col-sub {
            font-size: 12px;
            color: var(--md-on-surface-variant);
            margin-bottom: 10px;
        }

        /* ---- Chat bubbles ---- */
        .bubble-user {
            background: var(--md-primary-container);
            color: var(--md-on-primary-container);
            padding: 12px 16px;
            border-radius: 20px 20px 4px 20px;
            margin: 8px 0 8px auto;
            max-width: 88%;
            font-size: 14px;
            line-height: 1.55;
            box-shadow: 0 1px 3px rgba(0,0,0,.06);
        }
        .bubble-assistant {
            background: #FFFFFF;
            color: var(--md-on-surface);
            padding: 14px 18px;
            border-radius: 20px 20px 20px 4px;
            margin: 8px 0;
            max-width: 92%;
            font-size: 14px;
            line-height: 1.6;
            border: 1px solid var(--md-outline-variant);
            box-shadow: 0 1px 4px rgba(0,0,0,.05);
        }
        .bubble-ts {
            font-size: 10px;
            color: var(--md-outline);
            margin-top: 4px;
            text-align: right;
        }

        /* ---- Token cards ---- */
        .token-card {
            background: linear-gradient(135deg, var(--md-tertiary-container) 0%, #E8F0FF 100%);
            border-radius: 14px;
            padding: 14px 18px;
            margin: 10px 0;
            border: 1px solid rgba(75,96,124,.12);
        }
        .token-card-title {
            font-size: 12px;
            font-weight: 600;
            color: var(--md-tertiary);
            text-transform: uppercase;
            letter-spacing: .6px;
            margin-bottom: 10px;
        }
        .token-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 3px 0;
            font-size: 13px;
            color: var(--md-on-surface);
        }
        .token-row span:last-child {
            font-weight: 600;
            font-variant-numeric: tabular-nums;
        }
        .token-divider {
            height: 1px;
            background: var(--md-outline-variant);
            margin: 6px 0;
        }
        .token-total {
            font-size: 14px;
            font-weight: 700;
            color: var(--md-primary);
        }

        /* ---- Agent chip ---- */
        .agent-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: var(--md-secondary-container);
            color: var(--md-secondary);
            padding: 5px 12px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            margin: 2px 0;
        }

        /* ---- Workflow timeline ---- */
        .wf-step {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 8px 0;
            font-size: 13px;
            color: var(--md-on-surface);
        }
        .wf-dot {
            width: 10px; height: 10px;
            border-radius: 50%;
            margin-top: 4px;
            flex-shrink: 0;
        }
        .wf-dot-active { background: var(--md-primary); }
        .wf-dot-done   { background: var(--md-success); }

        /* ---- Empty state ---- */
        .empty-state {
            text-align: center;
            padding: 80px 24px;
            color: var(--md-outline);
        }
        .empty-state .icon { font-size: 48px; margin-bottom: 12px; }
        .empty-state .title { font-size: 15px; font-weight: 600; }
        .empty-state .sub { font-size: 12px; margin-top: 6px; line-height: 1.5; }

        /* ---- Divider ---- */
        .md-divider {
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--md-outline-variant), transparent);
            margin: 14px 0;
        }

        /* ---- Custom scrollbar ---- */
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--md-outline-variant); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--md-outline); }

        /* Streamlit container border radius override */
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 16px !important;
        }
    </style>
    """, unsafe_allow_html=True)


# ============================================================================
# AGENT INTERACTION
# ============================================================================
def horizonagent(query: str) -> dict:
    """Run the 3Horizon agent and return structured results."""
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )

    results = {
        "final_response": "",
        "workflow_steps": [],
        "individual_agent_outputs": [],
        "debug_logs": [],
        "token_usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }

    with project_client:
        workflow = {"name": "3Horizon", "version": "1"}
        openai_client = project_client.get_openai_client()
        conversation = openai_client.conversations.create()
        results["debug_logs"].append(f"Conversation created (id: {conversation.id})")

        stream = openai_client.responses.create(
            conversation=conversation.id,
            extra_body={"agent_reference": {"name": workflow["name"], "type": "agent_reference"}},
            input=query,
            stream=True,
            metadata={"x-ms-debug-mode-enabled": "1"},
        )

        current_agent_id = None
        current_agent_text = ""

        for event in stream:
            if event.type == "response.output_text.done":
                results["final_response"] += event.text + "\n"
                if current_agent_id:
                    results["individual_agent_outputs"].append({
                        "agent_id": current_agent_id,
                        "output": event.text,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })

            elif (
                event.type == "response.output_item.added"
                and hasattr(event, "item")
                and getattr(event.item, "type", "") == "workflow_action"
            ):
                if current_agent_id and current_agent_text:
                    results["individual_agent_outputs"].append({
                        "agent_id": current_agent_id,
                        "output": current_agent_text,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                current_agent_id = event.item.action_id
                current_agent_text = ""
                results["workflow_steps"].append({
                    "action_id": event.item.action_id,
                    "status": "started",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                })
                results["debug_logs"].append(f"Agent '{event.item.action_id}' started")

            elif (
                event.type == "response.output_item.done"
                and hasattr(event, "item")
                and getattr(event.item, "type", "") == "workflow_action"
            ):
                if current_agent_text:
                    results["individual_agent_outputs"].append({
                        "agent_id": event.item.action_id,
                        "output": current_agent_text,
                        "status": event.item.status,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    current_agent_text = ""
                results["workflow_steps"].append({
                    "action_id": event.item.action_id,
                    "status": event.item.status,
                    "previous_action": getattr(event.item, "previous_action_id", None),
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                })
                results["debug_logs"].append(
                    f"Agent '{event.item.action_id}' completed ({event.item.status})"
                )

            elif event.type == "response.output_text.delta":
                current_agent_text += event.delta

            elif event.type == "response.completed":
                resp = event.response
                usage = getattr(resp, "usage", None)
                if usage:
                    results["token_usage"]["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
                    results["token_usage"]["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
                    results["token_usage"]["total_tokens"] = getattr(usage, "total_tokens", 0) or 0
                results["debug_logs"].append("Response completed")

            else:
                results["debug_logs"].append(f"Event: {event.type}")

        if current_agent_text and not results["final_response"].strip():
            results["final_response"] = current_agent_text

        results["debug_logs"].append("Conversation finished")

    return results


# ============================================================================
# SESSION STATE
# ============================================================================
def initialize_session_state():
    defaults = {
        "chat_history": [],
        "agent_results": [],
        "processing": False,
        "conversation_count": 0,
        "cumulative_tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================================
# RENDER HELPERS
# ============================================================================
def render_token_card(usage: dict, title: str = "Token Usage"):
    inp = usage.get("input_tokens", 0)
    out = usage.get("output_tokens", 0)
    total = usage.get("total_tokens", 0) or (inp + out)
    st.markdown(f"""
    <div class="token-card">
        <div class="token-card-title">{title}</div>
        <div class="token-row"><span>Input tokens</span><span>{inp:,}</span></div>
        <div class="token-row"><span>Output tokens</span><span>{out:,}</span></div>
        <div class="token-divider"></div>
        <div class="token-row"><span class="token-total">Total</span><span class="token-total">{total:,}</span></div>
    </div>
    """, unsafe_allow_html=True)


def render_chat_bubble(role: str, content: str, timestamp: str):
    cls = "bubble-user" if role == "user" else "bubble-assistant"
    icon = "👤" if role == "user" else "🤖"
    st.markdown(f"""
    <div class="{cls}">
        {content}
        <div class="bubble-ts">{icon} {timestamp}</div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================================
# MAIN UI
# ============================================================================
def main():
    st.set_page_config(
        page_title="3Horizon – Strategic Planning Agent",
        page_icon="🔭",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    apply_material_design_3()
    initialize_session_state()

    # ---- Top bar ----
    st.markdown("""
    <div class="horizon-topbar">
        <span style="font-size:36px;">🔭</span>
        <div>
            <h1>3 Horizon</h1>
            <p>Strategic Growth Planning Agent &nbsp;·&nbsp; Powered by Azure AI Foundry</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ---- Two-column layout with wide gap ----
    left_col, spacer, right_col = st.columns([5, 0.4, 4])

    # ======================= LEFT COLUMN – Chat =======================
    with left_col:
        st.markdown('<div class="col-header">💬 Conversation</div>', unsafe_allow_html=True)
        st.markdown('<div class="col-sub">Chat with the 3-Horizon strategic planning agent</div>', unsafe_allow_html=True)

        chat_container = st.container(height=500)
        with chat_container:
            if not st.session_state.chat_history:
                st.markdown("""
                <div class="empty-state">
                    <div class="icon">🔭</div>
                    <div class="title">Start a Conversation</div>
                    <div class="sub">
                        Ask about strategic growth horizons, innovation planning,<br>
                        or business portfolio analysis to get started.
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                for msg in st.session_state.chat_history:
                    render_chat_bubble(msg["role"], msg["content"], msg["timestamp"])

                # Show token summary at the bottom of the last assistant reply
                if st.session_state.agent_results:
                    last = st.session_state.agent_results[-1]
                    usage = last.get("token_usage", {})
                    if usage.get("total_tokens", 0) or usage.get("input_tokens", 0):
                        render_token_card(usage, "Last Response Tokens")

        # Processing indicator
        if st.session_state.processing:
            st.info("⏳ 3Horizon is thinking…")

    # ======================= RIGHT COLUMN – Outputs =======================
    with right_col:
        st.markdown('<div class="col-header">📊 Agent Insights</div>', unsafe_allow_html=True)
        st.markdown('<div class="col-sub">Token usage, workflow steps &amp; individual agent outputs</div>', unsafe_allow_html=True)

        output_container = st.container(height=500)
        with output_container:
            if not st.session_state.agent_results:
                st.markdown("""
                <div class="empty-state">
                    <div class="icon">📊</div>
                    <div class="title">No Results Yet</div>
                    <div class="sub">
                        Agent responses, workflow steps and<br>
                        token statistics will appear here.
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                latest = st.session_state.agent_results[-1]

                # -- Cumulative token usage --
                render_token_card(st.session_state.cumulative_tokens, "📈 Cumulative Token Usage")

                # -- Per-request token usage --
                req_usage = latest.get("token_usage", {})
                if req_usage.get("total_tokens", 0) or req_usage.get("input_tokens", 0):
                    render_token_card(req_usage, "🔄 Last Request Tokens")

                st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)

                # -- Workflow steps --
                steps = latest.get("workflow_steps", [])
                if steps:
                    with st.expander("⚙️ Workflow Steps", expanded=False):
                        for step in steps:
                            done = step.get("status") in ("completed", "done")
                            dot = "wf-dot-done" if done else "wf-dot-active"
                            icon = "✅" if done else "🔄"
                            st.markdown(f"""
                            <div class="wf-step">
                                <div class="wf-dot {dot}"></div>
                                <div><strong>{step.get('action_id','—')}</strong>
                                &nbsp;<span class="agent-chip">{icon} {step.get('status','—')}</span>
                                <span style="font-size:11px;color:var(--md-outline);margin-left:6px;">{step.get('timestamp','')}</span></div>
                            </div>
                            """, unsafe_allow_html=True)

                # -- Individual agent outputs --
                agent_outputs = latest.get("individual_agent_outputs", [])
                if agent_outputs:
                    st.markdown(
                        '<div class="col-header" style="font-size:13px;margin-top:8px;">🤖 Individual Agent Outputs</div>',
                        unsafe_allow_html=True,
                    )
                    for idx, ao in enumerate(agent_outputs):
                        agent_id = ao.get("agent_id", f"Agent {idx + 1}")
                        status = ao.get("status", "completed")
                        ts = ao.get("timestamp", "")
                        icon = "✅" if status == "completed" else "🔄"
                        with st.expander(f"{icon} {agent_id}  ·  {ts}", expanded=False):
                            st.markdown(ao.get("output", "_No output captured_"))

                # -- Debug logs --
                debug = latest.get("debug_logs", [])
                if debug:
                    with st.expander("🔧 Debug Logs", expanded=False):
                        for log in debug:
                            st.text(log)

    # ---- Spacer column is intentionally empty ----
    with spacer:
        st.empty()

    # ======================= CHAT INPUT =======================
    user_input = st.chat_input(
        placeholder="Ask about strategic horizons, innovation, or growth planning…",
        disabled=st.session_state.processing,
    )

    if user_input:
        ts = datetime.now().strftime("%H:%M:%S")
        st.session_state.chat_history.append({"role": "user", "content": user_input, "timestamp": ts})
        st.session_state.processing = True
        st.session_state.conversation_count += 1

        try:
            start = time.time()
            results = horizonagent(user_input)
            elapsed = time.time() - start

            # Store results
            st.session_state.agent_results.append(results)

            # Accumulate tokens
            for k in ("input_tokens", "output_tokens", "total_tokens"):
                st.session_state.cumulative_tokens[k] += results["token_usage"].get(k, 0)

            # Build the assistant message
            summary = results.get("final_response", "").strip() or "Analysis complete."
            summary += f"\n\n_Completed in {elapsed:.1f}s_"
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": summary,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })

        except Exception as e:
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": f"❌ Error: {e}",
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            })
        finally:
            st.session_state.processing = False
            st.rerun()

    # ======================= SIDEBAR =======================
    with st.sidebar:
        st.markdown("### ⚙️ 3Horizon Settings")
        st.markdown("---")

        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.agent_results = []
            st.session_state.cumulative_tokens = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            st.session_state.conversation_count = 0
            st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Session Stats")
        st.metric("Conversations", st.session_state.conversation_count)
        st.metric("Messages", len(st.session_state.chat_history))
        cum = st.session_state.cumulative_tokens
        st.metric("Total Tokens", f"{cum['total_tokens']:,}")

        st.markdown("---")
        st.caption("3Horizon v1.0 · Azure AI Foundry")


if __name__ == "__main__":
    main()