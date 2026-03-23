import asyncio
import json
import logging
import os
import time as _time
from typing import cast
from datetime import datetime

import streamlit as st
from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Message,
    WorkflowEvent,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatRequestSentEvent, MagenticBuilder, MagenticProgressLedger
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

# ── Streamlit page config ──
st.set_page_config(
    page_title="Retail Bidding Agent",
    page_icon="🛒",
    layout="wide",
)

# ── Light & elegant custom CSS ──
st.markdown("""
<style>
    /* Page background */
    .stApp { background-color: #f7f9fc; }

    /* Chat bubbles */
    .user-bubble {
        background: linear-gradient(135deg, #4a90d9 0%, #357abd 100%);
        color: #ffffff;
        padding: 12px 18px;
        border-radius: 18px 18px 4px 18px;
        margin: 6px 0;
        max-width: 85%;
        margin-left: auto;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .assistant-bubble {
        background: #ffffff;
        color: #1e293b;
        padding: 12px 18px;
        border-radius: 18px 18px 18px 4px;
        margin: 6px 0;
        max-width: 85%;
        border: 1px solid #e2e8f0;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .agent-label {
        font-size: 0.75rem;
        font-weight: 600;
        color: #64748b;
        margin-bottom: 2px;
    }

    /* Sidebar / expander styling */
    .stExpander { border: 1px solid #e2e8f0 !important; border-radius: 10px !important; }

    /* Title styling */
    .main-title {
        text-align: center;
        color: #1e3a5f;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        text-align: center;
        color: #64748b;
        font-size: 0.9rem;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ── Session state init ──
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent_outputs" not in st.session_state:
    st.session_state.agent_outputs = []
if "plans" not in st.session_state:
    st.session_state.plans = []
if "ledgers" not in st.session_state:
    st.session_state.ledgers = []
if "token_usage" not in st.session_state:
    st.session_state.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
if "processing" not in st.session_state:
    st.session_state.processing = False


@st.cache_resource
def get_client():
    return AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )


client = get_client()


# ── Agent logic (unchanged) ──
async def bidding(query: str, stream_placeholder):
    """Run the Magentic-One bidding workflow and stream results into the UI."""
    walmart_agent = Agent(
        name="walmart_agent",
        description="Provide product and price information to agents.",
        instructions=(
            """You are a Retail Walmart Agent. Provide real-time product and price information to agents. 
            Also provide available quantity and shipping information. 
            If you don't know the answer, say you don't know. 
            Always provide the most accurate and up-to-date information. Be concise and to the point.
            """
        ),
        client=client,
    )

    amazon_agent = Agent(
        name="amazon_agent",
        description="Provide product and price information to agents.",
        instructions=(
            """You are a Retail Amazon Agent. Provide real-time product and price information to agents. 
            Also provide available quantity and shipping information. 
            If you don't know the answer, say you don't know. 
            Always provide the most accurate and up-to-date information. Be concise and to the point.
            """
        ),
        client=client,
    )

    bidding_agent = Agent(
        name="bidding_agent",
        description="Bid all agents and find the best deals.",
        instructions=(
            """You are a Retail Bidding Agent. Get the product and price, quantity from vendor agents. 
            Compare the prices, quantity and shipping information and find the best deal for the user.
            If you don't know the answer, say you don't know. 
            Find the best deal and provide it to the user. Be concise and to the point.
            """
        ),
        client=client,
    )

    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates the walmart, amazon, and bidding workflow",
        instructions="You coordinate a team to complete complex tasks efficiently.",
        client=client,
    )

    workflow = MagenticBuilder(
        participants=[walmart_agent, amazon_agent, bidding_agent],
        intermediate_outputs=True,
        manager_agent=manager_agent,
        max_round_count=10,
        max_stall_count=3,
        max_reset_count=2,
    ).build()

    # Collectors for right-panel data
    agent_streams: dict[str, str] = {}  # agent_name -> accumulated text
    plans: list[str] = []
    ledgers: list[dict] = []

    last_message_id: str | None = None
    output_event: WorkflowEvent | None = None

    # Use the pre-created placeholder inside the right details container

    def _render_agent_streams():
        """Re-render the live agent streaming area inside the right details container."""
        md = ""
        for name, text in agent_streams.items():
            md += f"**🤖 {name}**\n\n{text}\n\n---\n\n"
        stream_placeholder.markdown(md)

    async for event in workflow.run(query, stream=True):
        if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
            message_id = event.data.message_id
            agent_name = event.executor_id or "agent"
            if agent_name not in agent_streams:
                agent_streams[agent_name] = ""
            agent_streams[agent_name] += str(event.data)
            _render_agent_streams()

            if message_id != last_message_id:
                last_message_id = message_id

        elif event.type == "magentic_orchestrator":
            if isinstance(event.data.content, Message):
                plans.append(event.data.content.text)
            elif isinstance(event.data.content, MagenticProgressLedger):
                ledgers.append(event.data.content.to_dict())
            # No blocking input – this is a UI app

        elif event.type == "output":
            output_event = event

    # Extract final output
    final_output = ""
    if output_event and output_event.data:
        output_messages = cast(list[Message], output_event.data)
        if output_messages:
            final_output = output_messages[-1].text

    # Clear streaming area and show final in left history
    stream_placeholder.empty()

    return final_output, agent_streams, plans, ledgers

def main():
    
    # ── Header ──
    st.markdown('<h2 class="main-title">🛒 Retail Bidding Agent</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Compare prices across retailers &mdash; powered by Magentic-One multi-agent orchestration</p>', unsafe_allow_html=True)

    # ── Two-column layout ──
    left_col, right_col = st.columns([3, 2], gap="medium")

    # ── LEFT: Conversation history ──
    with left_col:
        st.markdown("##### 💬 Conversation")
        history_container = st.container(height=500)
        with history_container:
            for msg in st.session_state.messages:
                if msg["role"] == "user":
                    st.markdown(f'<div class="agent-label">You</div><div class="user-bubble">{msg["content"]}</div>', unsafe_allow_html=True)
                else:
                    label = msg.get("agent", "Assistant")
                    st.markdown(f'<div class="agent-label">{label}</div><div class="assistant-bubble">{msg["content"]}</div>', unsafe_allow_html=True)

    # ── RIGHT: Details panel ──
    with right_col:
        st.markdown("##### 📊 Details")
        details_container = st.container(height=500)
        with details_container:
            # Token usage expander
            with st.expander("🔢 Token Usage", expanded=False):
                tu = st.session_state.token_usage
                c1, c2, c3 = st.columns(3)
                c1.metric("Prompt", f"{tu['prompt_tokens']:,}")
                c2.metric("Completion", f"{tu['completion_tokens']:,}")
                c3.metric("Total", f"{tu['total_tokens']:,}")

            # Plans
            if st.session_state.plans:
                with st.expander("📋 Orchestration Plans", expanded=False):
                    for i, plan in enumerate(st.session_state.plans, 1):
                        st.markdown(f"**Plan {i}**")
                        st.markdown(plan)
                        if i < len(st.session_state.plans):
                            st.divider()

            # Ledgers
            if st.session_state.ledgers:
                with st.expander("📒 Progress Ledgers", expanded=False):
                    for i, ledger in enumerate(st.session_state.ledgers, 1):
                        st.markdown(f"**Ledger {i}**")
                        st.json(ledger)

            # Individual agent outputs – each agent in its own expander
            if st.session_state.agent_outputs:
                for name, text in st.session_state.agent_outputs:
                    with st.expander(f"🤖 {name}", expanded=True):
                        st.markdown(text)
            # Pre-create streaming placeholder inside this container
            stream_placeholder = st.empty()

    # ── Chat input (always at bottom) ──
    user_input = st.chat_input("Ask about a product to compare prices…")

    if user_input and not st.session_state.processing:
        st.session_state.processing = True

        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_input})

        # Reset per-query right-panel data
        st.session_state.agent_outputs = []
        st.session_state.plans = []
        st.session_state.ledgers = []

        with left_col:
            with history_container:
                st.markdown(f'<div class="agent-label">You</div><div class="user-bubble">{user_input}</div>', unsafe_allow_html=True)

        # Run workflow with spinner
        with left_col:
            with st.spinner("Agents are working on your request…", show_time=True):
                start = _time.time()
                final_output, agent_streams, plans, ledgers = asyncio.run(
                    bidding(user_input, stream_placeholder)
                )
                elapsed = _time.time() - start

        # Estimate token usage (rough heuristic: ~4 chars per token)
        all_text = final_output + " ".join(agent_streams.values())
        est_total = max(1, len(all_text) // 4)
        est_prompt = est_total // 3
        est_completion = est_total - est_prompt
        st.session_state.token_usage = {
            "prompt_tokens": st.session_state.token_usage["prompt_tokens"] + est_prompt,
            "completion_tokens": st.session_state.token_usage["completion_tokens"] + est_completion,
            "total_tokens": st.session_state.token_usage["total_tokens"] + est_total,
        }

        # Store results
        st.session_state.messages.append({"role": "assistant", "content": final_output, "agent": "Bidding Summary"})
        st.session_state.agent_outputs = [(name, text) for name, text in agent_streams.items()]
        st.session_state.plans = plans
        st.session_state.ledgers = ledgers
        st.session_state.processing = False

        st.rerun()

if __name__ == "__main__":
    main()