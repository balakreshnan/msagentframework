import logging
import json
import io
import streamlit as st
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
import os
from dotenv import load_dotenv
from datetime import datetime
import time
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

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
# ASSESSMENT HELPERS
# ============================================================================
def load_assessment_data():
    """Load the 3horizon.json assessment file."""
    json_path = os.path.join(os.path.dirname(__file__), "data", "3horizon.json")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_assessment_summary(assessment_data, slider_values):
    """Build a structured summary of slider values organized by phase."""
    summary_lines = []
    for phase in assessment_data.get("phases", []):
        summary_lines.append(f"\n## {phase['title']}")
        summary_lines.append(f"_{phase['description']}_")
        for q in phase.get("questions", []):
            qid = q["id"]
            val = slider_values.get(qid, 5)
            summary_lines.append(f"- **{q['text']}** → Score: {val}/10")
    return "\n".join(summary_lines)


def run_assessment_analysis(summary_text: str) -> str:
    """Send assessment results to LLM for quadrant analysis and recommendations."""
    project_client = AIProjectClient(
        endpoint=myEndpoint,
        credential=DefaultAzureCredential(),
    )

    prompt = f"""You are a senior strategy consultant specializing in the McKinsey Three Horizons framework.

A client has completed a self-assessment. Each area was scored 1-10 (1 = very low maturity, 10 = best-in-class).

Here are the results:
{summary_text}

Based on these scores, provide your analysis in the following EXACT JSON structure (no markdown fencing, just raw JSON):
{{
  "quadrant_items": [
    {{
      "label": "<short label, max 6 words>",
      "impact": <float 1-10, business impact potential>,
      "readiness": <float 1-10, current organizational readiness>,
      "horizon": "<H1|H2|H3>",
      "size": <float 1-5, relative priority weight>
    }}
  ],
  "recommendations": [
    {{
      "horizon": "<H1|H2|H3>",
      "title": "<recommendation title>",
      "description": "<2-3 sentence recommendation>",
      "priority": "<High|Medium|Low>",
      "timeframe": "<0-6 months|6-18 months|18-36 months>"
    }}
  ],
  "overall_summary": "<A 3-4 sentence executive summary of the organization's AI readiness and strategic positioning>"
}}

Generate 8-12 quadrant items spread across all three horizons, and 6-9 recommendations (2-3 per horizon).
Ensure impact and readiness values create a meaningful spread across the quadrant.
"""

    with project_client:
        openai_client = project_client.get_openai_client()
        response = openai_client.responses.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
            input=prompt,
        )
        return response.output_text


def parse_llm_json(raw_text: str) -> dict:
    """Parse JSON from LLM response, handling markdown fencing."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text)


def render_quadrant_chart(items: list):
    """Render a matplotlib quadrant scatter chart from quadrant_items."""
    fig, ax = plt.subplots(figsize=(9, 7))

    horizon_colors = {"H1": "#006A6A", "H2": "#4B607C", "H3": "#BA1A1A"}
    horizon_labels = {"H1": "Horizon 1 – Optimize", "H2": "Horizon 2 – Grow", "H3": "Horizon 3 – Transform"}

    # Draw quadrant lines and background
    ax.axhline(y=5.5, color="#BEC9C8", linestyle="--", linewidth=1)
    ax.axvline(x=5.5, color="#BEC9C8", linestyle="--", linewidth=1)

    # Quadrant labels
    ax.text(2.75, 9.6, "High Impact / Low Readiness\n(Invest & Build)", ha="center", fontsize=8, color="#6F7979", style="italic")
    ax.text(8, 9.6, "High Impact / High Readiness\n(Accelerate Now)", ha="center", fontsize=8, color="#6F7979", style="italic")
    ax.text(2.75, 0.4, "Low Impact / Low Readiness\n(Deprioritize)", ha="center", fontsize=8, color="#6F7979", style="italic")
    ax.text(8, 0.4, "Low Impact / High Readiness\n(Quick Wins)", ha="center", fontsize=8, color="#6F7979", style="italic")

    plotted_horizons = set()
    for item in items:
        h = item.get("horizon", "H1")
        color = horizon_colors.get(h, "#006A6A")
        size = item.get("size", 2) * 80
        ax.scatter(
            item["readiness"], item["impact"],
            s=size, c=color, alpha=0.75, edgecolors="white", linewidth=1.5, zorder=5,
        )
        ax.annotate(
            item["label"], (item["readiness"], item["impact"]),
            textcoords="offset points", xytext=(8, 6), fontsize=7.5, color="#161D1D",
        )
        plotted_horizons.add(h)

    legend_patches = [mpatches.Patch(color=horizon_colors[h], label=horizon_labels[h]) for h in sorted(plotted_horizons)]
    ax.legend(handles=legend_patches, loc="lower left", fontsize=8, framealpha=0.9)

    ax.set_xlim(0.5, 10.5)
    ax.set_ylim(0.5, 10.5)
    ax.set_xlabel("Organizational Readiness →", fontsize=10, fontweight="bold")
    ax.set_ylabel("Business Impact Potential →", fontsize=10, fontweight="bold")
    ax.set_title("Three Horizons Strategic Quadrant", fontsize=13, fontweight="bold", pad=14)
    ax.set_facecolor("#F5FAFA")
    fig.patch.set_facecolor("#F5FAFA")
    ax.grid(True, alpha=0.15)
    fig.tight_layout()
    return fig


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
        "assessment_sliders": {},
        "assessment_result": None,
        "assessment_processing": False,
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

    # ---- Tabs ----
    tab_chat, tab_assess = st.tabs(["💬 Strategy Chat", "📋 Self-Assessment"])

    # ======================= TAB 1 – Chat =======================
    with tab_chat:
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

        # ---- Chat Input (inside tab_chat) ----
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

                st.session_state.agent_results.append(results)

                for k in ("input_tokens", "output_tokens", "total_tokens"):
                    st.session_state.cumulative_tokens[k] += results["token_usage"].get(k, 0)

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

    # ======================= TAB 2 – Self-Assessment =======================
    with tab_assess:
        assessment_data = load_assessment_data()

        st.markdown("""
        <div style="background:var(--md-secondary-container);padding:14px 20px;border-radius:14px;margin-bottom:16px;">
            <strong style="color:var(--md-secondary);">📋 Three Horizons Self-Assessment</strong><br>
            <span style="font-size:13px;color:var(--md-on-surface-variant);">
                Rate your organization on each area using the sliders (1 = very low maturity, 10 = best-in-class).
                Once complete, click <b>Analyze</b> to generate a strategic quadrant and recommendations.
            </span>
        </div>
        """, unsafe_allow_html=True)

        assess_left, assess_spacer, assess_right = st.columns([5, 0.3, 5])

        # -- LEFT: Sliders --
        with assess_left:
            phases = assessment_data.get("phases", [])
            half = (len(phases) + 1) // 2
            for phase in phases[:half]:
                with st.expander(f"🔹 {phase['title']}", expanded=True):
                    st.caption(phase["description"])
                    for q in phase.get("questions", []):
                        qid = q["id"]
                        req_marker = " *" if q.get("required") else ""
                        st.session_state.assessment_sliders[qid] = st.slider(
                            f"{q['text']}{req_marker}",
                            min_value=1, max_value=10,
                            value=st.session_state.assessment_sliders.get(qid, 5),
                            help=q.get("why", ""),
                            key=f"slider_{qid}",
                        )

        with assess_spacer:
            st.empty()

        with assess_right:
            for phase in phases[half:]:
                with st.expander(f"🔹 {phase['title']}", expanded=True):
                    st.caption(phase["description"])
                    for q in phase.get("questions", []):
                        qid = q["id"]
                        req_marker = " *" if q.get("required") else ""
                        st.session_state.assessment_sliders[qid] = st.slider(
                            f"{q['text']}{req_marker}",
                            min_value=1, max_value=10,
                            value=st.session_state.assessment_sliders.get(qid, 5),
                            help=q.get("why", ""),
                            key=f"slider_{qid}",
                        )

        st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)

        # -- Analyze button --
        btn_col1, btn_col2, btn_col3 = st.columns([3, 2, 3])
        with btn_col2:
            analyze_clicked = st.button(
                "🚀 Analyze & Generate Quadrant",
                use_container_width=True,
                type="primary",
                disabled=st.session_state.assessment_processing,
            )

        if analyze_clicked:
            # Collect current slider values from widget keys
            for phase in assessment_data.get("phases", []):
                for q in phase.get("questions", []):
                    qid = q["id"]
                    widget_key = f"slider_{qid}"
                    if widget_key in st.session_state:
                        st.session_state.assessment_sliders[qid] = st.session_state[widget_key]

            st.session_state.assessment_processing = True
            summary = build_assessment_summary(assessment_data, st.session_state.assessment_sliders)
            with st.spinner("🔭 Analyzing your assessment with AI…", show_time=True):
                try:
                    raw = run_assessment_analysis(summary)
                    result = parse_llm_json(raw)
                    st.session_state.assessment_result = result
                    st.session_state.assessment_processing = False
                    st.rerun()
                except Exception as e:
                    st.session_state.assessment_processing = False
                    st.error(f"Analysis failed: {e}")
                    with st.expander("🔧 Debug: Raw LLM Response", expanded=False):
                        st.code(raw if 'raw' in dir() else "No response received", language="json")

        # -- Results --
        if st.session_state.assessment_result:
            result = st.session_state.assessment_result

            # Executive summary
            overall = result.get("overall_summary", "")
            if overall:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg, var(--md-primary-container) 0%, #E8F0FF 100%);
                            padding:16px 22px;border-radius:16px;margin:12px 0 18px;
                            border:1px solid rgba(0,106,106,.12);">
                    <strong style="color:var(--md-primary);font-size:14px;">📝 Executive Summary</strong><br>
                    <span style="font-size:13px;color:var(--md-on-surface);line-height:1.6;">{overall}</span>
                </div>
                """, unsafe_allow_html=True)

            # Quadrant chart
            quadrant_items = result.get("quadrant_items", [])
            if quadrant_items:
                st.markdown('<div class="col-header">📊 Strategic Quadrant</div>', unsafe_allow_html=True)
                fig = render_quadrant_chart(quadrant_items)
                st.pyplot(fig)
                plt.close(fig)

            # Recommendations by horizon
            recommendations = result.get("recommendations", [])
            if recommendations:
                st.markdown('<div class="col-header" style="margin-top:16px;">💡 Recommendations</div>', unsafe_allow_html=True)

                rec_cols = st.columns(3)
                horizon_map = {"H1": 0, "H2": 1, "H3": 2}
                horizon_titles = {
                    "H1": "🟢 Horizon 1 – Optimize & Defend",
                    "H2": "🔵 Horizon 2 – Build & Grow",
                    "H3": "🔴 Horizon 3 – Explore & Transform",
                }
                priority_colors = {"High": "#BA1A1A", "Medium": "#7C5800", "Low": "#006D3B"}

                for h_key, col_idx in horizon_map.items():
                    h_recs = [r for r in recommendations if r.get("horizon") == h_key]
                    with rec_cols[col_idx]:
                        st.markdown(f"**{horizon_titles.get(h_key, h_key)}**")
                        if not h_recs:
                            st.caption("No recommendations for this horizon.")
                        for rec in h_recs:
                            p_color = priority_colors.get(rec.get("priority", "Medium"), "#7C5800")
                            st.markdown(f"""
                            <div style="background:#FFFFFF;border:1px solid var(--md-outline-variant);
                                        border-radius:12px;padding:12px 16px;margin-bottom:10px;">
                                <div style="font-size:13px;font-weight:600;color:var(--md-on-surface);">
                                    {rec.get('title','')}
                                </div>
                                <div style="font-size:12px;color:var(--md-on-surface-variant);margin-top:4px;line-height:1.5;">
                                    {rec.get('description','')}
                                </div>
                                <div style="display:flex;gap:8px;margin-top:8px;">
                                    <span style="font-size:10px;background:{p_color};color:white;
                                                 padding:2px 8px;border-radius:6px;">
                                        {rec.get('priority','Medium')} Priority
                                    </span>
                                    <span style="font-size:10px;background:var(--md-surface-variant);
                                                 padding:2px 8px;border-radius:6px;color:var(--md-on-surface-variant);">
                                        ⏱ {rec.get('timeframe','')}
                                    </span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

            # Reset button
            st.markdown('<div class="md-divider"></div>', unsafe_allow_html=True)
            reset_col1, reset_col2, reset_col3 = st.columns([3, 2, 3])
            with reset_col2:
                if st.button("🔄 Reset Assessment", use_container_width=True):
                    st.session_state.assessment_sliders = {}
                    st.session_state.assessment_result = None
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

        if st.button("🔄 Reset Assessment", use_container_width=True):
            st.session_state.assessment_sliders = {}
            st.session_state.assessment_result = None
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