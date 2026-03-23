import asyncio
import json
import logging
import os
import random
import time as _time
from typing import Annotated, cast
from datetime import datetime

import streamlit as st
from pydantic import Field
from agent_framework import (
    Agent,
    AgentResponseUpdate,
    Message,
    WorkflowEvent,
)
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatRequestSentEvent, MagenticBuilder, MagenticProgressLedger
from azure.identity import DefaultAzureCredential
from agent_framework import tool
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


# ── Negotiator tool functions ──
@tool(approval_mode="never_require")
def walmart_negotiate(
    product_name: Annotated[str, Field(description="Name of the product to negotiate.")],
    quantity: Annotated[float, Field(description="Number of units requested.")],
    delivery_zip: Annotated[str, Field(description="ZIP code for delivery.")],
    delivery_days: Annotated[float, Field(description="Requested delivery window in days.")],
    current_offer: Annotated[float, Field(description="The current competing offer price per unit to beat. Use 0 if unknown.")],
) -> str:
    """Negotiate with Walmart for a product. Returns Walmart's counter-offer including unit price, shipping cost, and delivery estimate."""
    try:
        quantity = int(quantity)
        delivery_days = int(delivery_days)
        current_offer = float(current_offer)

        base_prices = {
            "strawberries": 4.99, "blueberries": 5.49, "raspberries": 6.29,
            "bananas": 0.79, "apples": 1.49, "oranges": 1.29,
            "milk": 3.99, "bread": 2.99, "eggs": 3.49,
            "chicken breast": 8.99, "ground beef": 6.99, "salmon": 12.99,
        }
        product_lower = product_name.lower()
        base = next((v for k, v in base_prices.items() if k in product_lower), round(random.uniform(3.0, 15.0), 2))

        if quantity >= 100:
            discount = 0.20
        elif quantity >= 50:
            discount = 0.12
        elif quantity >= 24:
            discount = 0.08
        elif quantity >= 12:
            discount = 0.05
        else:
            discount = 0.0

        unit_price = round(base * (1 - discount), 2)

        if current_offer > 0 and unit_price > current_offer:
            price_cut = round(random.uniform(0.02, 0.10) * unit_price, 2)
            unit_price = round(max(unit_price - price_cut, base * 0.70), 2)

        if delivery_days <= 1:
            shipping = round(9.99 + quantity * 0.15, 2)
        elif delivery_days <= 3:
            shipping = round(5.99 + quantity * 0.08, 2)
        else:
            shipping = round(max(0.0, 2.99 - (quantity * 0.02)), 2)

        total = round(unit_price * quantity + shipping, 2)
        est_delivery = min(delivery_days, random.choice([1, 2, 3, 5]))

        return json.dumps({
            "retailer": "Walmart",
            "product": product_name,
            "unit_price": unit_price,
            "quantity": quantity,
            "subtotal": round(unit_price * quantity, 2),
            "shipping_cost": shipping,
            "total_price": total,
            "estimated_delivery_days": est_delivery,
            "delivery_zip": delivery_zip,
            "discount_applied": f"{discount*100:.0f}%",
            "notes": "Price valid for 30 minutes. Bulk orders may qualify for additional savings."
        })
    except Exception as e:
        return json.dumps({"retailer": "Walmart", "error": str(e)})

@tool(approval_mode="never_require")
def amazon_negotiate(
    product_name: Annotated[str, Field(description="Name of the product to negotiate.")],
    quantity: Annotated[float, Field(description="Number of units requested.")],
    delivery_zip: Annotated[str, Field(description="ZIP code for delivery.")],
    delivery_days: Annotated[float, Field(description="Requested delivery window in days.")],
    current_offer: Annotated[float, Field(description="The current competing offer price per unit to beat. Use 0 if unknown.")],
) -> str:
    """Negotiate with Amazon for a product. Returns Amazon's counter-offer including unit price, shipping cost, and delivery estimate."""
    try:
        quantity = int(quantity)
        delivery_days = int(delivery_days)
        current_offer = float(current_offer)

        base_prices = {
            "strawberries": 5.29, "blueberries": 5.99, "raspberries": 6.49,
            "bananas": 0.69, "apples": 1.59, "oranges": 1.19,
            "milk": 4.29, "bread": 3.29, "eggs": 3.29,
            "chicken breast": 9.49, "ground beef": 7.49, "salmon": 13.49,
        }
        product_lower = product_name.lower()
        base = next((v for k, v in base_prices.items() if k in product_lower), round(random.uniform(3.5, 16.0), 2))

        if quantity >= 100:
            discount = 0.22
        elif quantity >= 50:
            discount = 0.15
        elif quantity >= 24:
            discount = 0.10
        elif quantity >= 12:
            discount = 0.06
        elif quantity >= 5:
            discount = 0.03
        else:
            discount = 0.0

        unit_price = round(base * (1 - discount), 2)

        if current_offer > 0 and unit_price > current_offer:
            price_cut = round(random.uniform(0.03, 0.12) * unit_price, 2)
            unit_price = round(max(unit_price - price_cut, base * 0.68), 2)

        if delivery_days <= 1:
            shipping = round(7.99 + quantity * 0.10, 2)
        elif delivery_days <= 2:
            shipping = round(3.99 + quantity * 0.05, 2)
        else:
            shipping = 0.00

        total = round(unit_price * quantity + shipping, 2)
        est_delivery = min(delivery_days, random.choice([1, 2, 2, 3]))

        return json.dumps({
            "retailer": "Amazon",
            "product": product_name,
            "unit_price": unit_price,
            "quantity": quantity,
            "subtotal": round(unit_price * quantity, 2),
            "shipping_cost": shipping,
            "total_price": total,
            "estimated_delivery_days": est_delivery,
            "delivery_zip": delivery_zip,
            "discount_applied": f"{discount*100:.0f}%",
            "notes": "Prime members get free same-day delivery on eligible items. Subscribe & Save for extra 5% off."
        })
    except Exception as e:
        return json.dumps({"retailer": "Amazon", "error": str(e)})


# ── Agent logic (unchanged) ──
async def bidding(query: str, stream_placeholder):
    """Run the Magentic-One bidding workflow and stream results into the UI."""
    walmart_agent = Agent(
        name="walmart_agent",
        description="Walmart retail agent that provides product pricing, availability, and negotiates competitive deals.",
        instructions=(
            """You are a Retail Walmart Agent with access to the following Walmart pricing data.

            BASE PRICES (per unit):
            - Strawberries: $4.99, Blueberries: $5.49, Raspberries: $6.29
            - Bananas: $0.79, Apples: $1.49, Oranges: $1.29
            - Milk: $3.99, Bread: $2.99, Eggs: $3.49
            - Chicken Breast: $8.99, Ground Beef: $6.99, Salmon: $12.99
            - For any other product, use a reasonable price between $3.00 and $15.00.

            VOLUME DISCOUNTS:
            - 100+ units: 20% off
            - 50-99 units: 12% off
            - 24-49 units: 8% off
            - 12-23 units: 5% off
            - Under 12: no discount

            SHIPPING RATES:
            - Same-day (1 day): $9.99 + $0.15/unit
            - Express (2-3 days): $5.99 + $0.08/unit
            - Standard (4+ days): $2.99 (free on large orders)

            NEGOTIATION RULES:
            - You CAN lower your price when a competing offer is presented.
            - Your minimum price floor is 70% of the base price (after volume discount).
            - When the competitor's price is lower, reduce your price by 2-10% to try to match or beat it.
            - Always present your offer as JSON with: unit_price, quantity, subtotal, shipping_cost, total_price, estimated_delivery_days, discount_applied.
            - Be competitive and try to win the deal! Offer bundle deals or loyalty perks if needed.
            - If the user provides a ZIP code or delivery timeframe, incorporate it.
            """
        ),
        tool=walmart_negotiate,
        client=client,
    )

    amazon_agent = Agent(
        name="amazon_agent",
        description="Amazon retail agent that provides product pricing, availability, and negotiates competitive deals.",
        instructions=(
            """You are a Retail Amazon Agent with access to the following Amazon pricing data.

            BASE PRICES (per unit):
            - Strawberries: $5.29, Blueberries: $5.99, Raspberries: $6.49
            - Bananas: $0.69, Apples: $1.59, Oranges: $1.19
            - Milk: $4.29, Bread: $3.29, Eggs: $3.29
            - Chicken Breast: $9.49, Ground Beef: $7.49, Salmon: $13.49
            - For any other product, use a reasonable price between $3.50 and $16.00.

            VOLUME DISCOUNTS (Subscribe & Save style):
            - 100+ units: 22% off
            - 50-99 units: 15% off
            - 24-49 units: 10% off
            - 12-23 units: 6% off
            - 5-11 units: 3% off
            - Under 5: no discount

            SHIPPING RATES:
            - Same-day (1 day): $7.99 + $0.10/unit
            - Prime 2-day: $3.99 + $0.05/unit
            - Standard (3+ days): FREE

            NEGOTIATION RULES:
            - You CAN lower your price when a competing offer is presented.
            - Your minimum price floor is 68% of the base price (after volume discount).
            - When the competitor's price is lower, reduce your price by 3-12% to try to match or beat it.
            - Always present your offer as JSON with: unit_price, quantity, subtotal, shipping_cost, total_price, estimated_delivery_days, discount_applied.
            - Be competitive! Mention Prime benefits, Subscribe & Save for extra 5% off, and fast delivery.
            - If the user provides a ZIP code or delivery timeframe, incorporate it.
            """
        ),
        tool=amazon_negotiate,
        client=client,
    )

    bidding_agent = Agent(
        name="bidding_agent",
        description="Bidding agent that drives a multi-round negotiation between Walmart and Amazon to get the best deal.",
        instructions=(
            """You are a Retail Bidding & Negotiation Agent. Your job is to drive a competitive negotiation
            between the walmart_agent and amazon_agent to get the BEST possible price for the user.

            NEGOTIATION STRATEGY:
            1. Start by asking BOTH agents for their initial offers (round 1).
            2. Compare the two offers and tell each agent what the other's best price is.
            3. Ask each agent to beat the competitor's price. Share the exact competing unit_price so they can undercut.
            4. Continue this back-and-forth for up to 23 rounds of negotiation.
            5. On each round, share the competing best price so agents can undercut each other.
            6. Track all offers in a running comparison table.
            7. Stop early only if both agents report the same price for 3 consecutive rounds (price floor reached).
            8. At the end, present a FINAL COMPARISON with:
               - Best unit price from each retailer
               - Shipping costs
               - Delivery timeline
               - Total cost
               - Your RECOMMENDATION for the best overall deal (considering price + shipping + speed).

            Always be transparent with the user about the negotiation progress.
            Format your final recommendation clearly with a winner and savings summary.
            """
        ),
        client=client,
    )

    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates a multi-round price negotiation between Walmart and Amazon agents, mediated by the bidding agent.",
        instructions=(
            """You coordinate a team of retail agents to negotiate the best deal for the user.

            WORKFLOW:
            1. The bidding_agent drives the negotiation process.
            2. The walmart_agent and amazon_agent each calculate and present competitive offers.
            3. Allow the bidding_agent to run up to 23 rounds of back-and-forth negotiation between the retailers.
            4. On each round, the bidding_agent should:
               a. Get/update offers from both retail agents
               b. Share the competing best price with each agent
               c. Ask them to beat it
            5. Let the negotiation continue until the bidding_agent determines the best possible price
               has been reached (prices converge or 23 rounds complete).
            6. The bidding_agent then delivers the final comparison and recommendation.

            Do NOT terminate early — let the full negotiation play out for maximum savings.
            Coordinate handoffs between agents efficiently.
            """
        ),
        client=client,
    )

    workflow = MagenticBuilder(
        participants=[walmart_agent, amazon_agent, bidding_agent],
        intermediate_outputs=True,
        manager_agent=manager_agent,
        max_round_count=25,
        max_stall_count=5,
        max_reset_count=3,
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