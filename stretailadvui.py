import asyncio
import concurrent.futures
import time
from typing import Dict, List, Tuple

import streamlit as st

import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Annotated, Dict, List, Any, Optional
from openai import AzureOpenAI
import pandas as pd
import requests
import streamlit as st
from utils import get_weather, fetch_stock_data

from agent_framework import ChatAgent, ChatMessage
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from azure.core.exceptions import IncompleteReadError, ServiceRequestError

try:
    import aiohttp  # type: ignore
except Exception:  # pragma: no cover
    aiohttp = None
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from agent_framework.observability import get_tracer, setup_observability
from pydantic import Field
from agent_framework import AgentRunUpdateEvent, WorkflowBuilder, WorkflowOutputEvent
from typing import Final

from agent_framework import (
    AgentExecutorRequest,
    AgentExecutorResponse,
    AgentRunResponse,
    AgentRunUpdateEvent,
    ChatMessage,
    Role,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    executor,
)

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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

def normalize_token_usage(usage) -> dict:
    """Normalize various usage objects/dicts into a standard dict.
    Returns {'prompt_tokens', 'completion_tokens', 'total_tokens'} or {} if unavailable.
    """
    try:
        if not usage:
            return {}
        # If it's already a dict, use it directly
        if isinstance(usage, dict):
            d = usage
        else:
            # Attempt attribute access (e.g., ResponseUsage pydantic model)
            d = {}
            for name in ("prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens"):
                val = getattr(usage, name, None)
                if val is not None:
                    d[name] = val

        prompt = int(d.get("prompt_tokens", d.get("input_tokens", 0)) or 0)
        completion = int(d.get("completion_tokens", d.get("output_tokens", 0)) or 0)
        total = int(d.get("total_tokens", prompt + completion) or 0)
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}
    except Exception:
        return {}


def normalize_text(obj: Any) -> str:
    """Best-effort extraction of human-readable text from various response shapes."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj

    # Common agent framework patterns
    for attr in ("output_text", "output", "content", "text", "message"):
        if hasattr(obj, attr):
            try:
                v = getattr(obj, attr)
                if isinstance(v, str):
                    return v
                if isinstance(v, bytes):
                    return v.decode(errors="ignore")
                if isinstance(v, list):
                    parts: list[str] = []
                    for item in v:
                        t = normalize_text(item)
                        if t:
                            parts.append(t)
                    if parts:
                        return "\n".join(parts)
            except Exception:
                pass

    # Pydantic-like models
    for meth in ("model_dump", "to_dict"):
        if hasattr(obj, meth):
            try:
                dumped = getattr(obj, meth)()
                return json.dumps(dumped, ensure_ascii=False)
            except Exception:
                pass

    # Dict / list fallback
    if isinstance(obj, (dict, list)):
        try:
            return json.dumps(obj, ensure_ascii=False)
        except Exception:
            return str(obj)

    return str(obj)

def get_chat_response_gpt5_response(query: str) -> str:
    returntxt = ""

    responseclient = AzureOpenAI(
        base_url = os.getenv("AZURE_OPENAI_ENDPOINT") + "/openai/v1/",  
        api_key= os.getenv("AZURE_OPENAI_KEY"),
        api_version="preview"
        )
    deployment = "gpt-5"

    prompt = """You are a brainstorming assistant. Given the following query, 
    provide creative ideas and suggestions.
    Here are the agents available to you:
    - Ideation Catalyst: Generates creative and innovative ideas.
    - Inquiry Specialist: Asks strategic follow-up questions to uncover insights.
    - Business Analyst: Analyzes market potential and financial viability.

    Based on the query, pick the most relevant agents to assist you in brainstorming.
    Query: {query}
    
    Respond only the agents to use as array of strings.
    """

    # Some new parameters!  
    response = responseclient.responses.create(
        input=prompt.format(query=query),
        model=deployment,
        reasoning={
            "effort": "medium",
            "summary": "auto" # auto, concise, or detailed 
        },
        text={
            "verbosity": "low" # New with GPT-5 models
        }
    )

    # # Token usage details
    usage = normalize_token_usage(response.usage)

    # print("--------------------------------")
    # print("Output:")
    # print(output_text)
    returntxt = response.output_text

    return returntxt, usage

# -------------------------------
# CONFIGURATION – UPDATE PATHS IF NEEDED
# -------------------------------
CUSTOMERS_CSV     = "data/customers.csv"
INVENTORY_CSV     = "data/inventory.csv"           # Your 150+ products file
CUST_HISTORY_CSV  = "data/custinv.csv"             # Your 120-row customer-product history

# Cached DataFrames
_customers_df: Optional[pd.DataFrame] = None
_inventory_df: Optional[pd.DataFrame] = None
_cust_history_df: Optional[pd.DataFrame] = None


# -------------------------------
# 1. Load & Cache Helper
# -------------------------------
def _load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {os.path.abspath(path)}")
    return pd.read_csv(path)


# -------------------------------
# 2. TOOL – Lookup Customer
# -------------------------------
def _get_customers_df() -> pd.DataFrame:
    global _customers_df
    if _customers_df is None:
        _customers_df = _load_csv(CUSTOMERS_CSV)
        _customers_df['Email'] = _customers_df['Email'].str.lower().str.strip()
        _customers_df['Phone'] = _customers_df['Phone'].astype(str).str.replace(r'\D', '', regex=True)
    return _customers_df


def lookup_customer(query: str) -> Optional[Dict[str, Any]]:
    """Search customer by ID, email, phone (last 7 digits), name, or loyalty ID."""
    df = _get_customers_df()
    q = str(query).strip().lower()

    # Exact matches first
    if q.startswith(("cust-", "ld-")):
        col = "Customer_ID" if q.startswith("cust") else "Loyalty_ID"
        row = df[df[col].str.upper() == q.upper()]
        if not row.empty:
            return row.iloc[0].to_dict()

    # Email
    row = df[df['Email'] == q]
    if not row.empty:
        return row.iloc[0].to_dict()

    # Phone (last 7+ digits)
    clean_phone = q.replace("-", "")
    mask = df['Phone'].str.contains(clean_phone[-7:], na=False)
    if mask.sum() == 1:
        return df[mask].iloc[0].to_dict()

    # Name
    name_match = df[df['First_Name'].str.lower().str.contains(q, na=False) |
                   df['Last_Name'].str.lower().str.contains(q, na=False)]
    if len(name_match) == 1:
        return name_match.iloc[0].to_dict()

    return None


# -------------------------------
# 3. TOOL – Inventory Lookup & Search
# -------------------------------
def _get_inventory_df() -> pd.DataFrame:
    global _inventory_df
    if _inventory_df is None:
        _inventory_df = _load_csv(INVENTORY_CSV)
    return _inventory_df


def lookup_inventory(
    query: Optional[str] = None,
    product_id: Optional[str] = None,
    category: Optional[str] = None,
    low_stock_only: bool = False,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Flexible inventory lookup.
    - By exact Product_ID → returns 1 item
    - By search term (name/category) → fuzzy search
    - By category only
    - low_stock_only = True → only items with Remaining_Quantity < 20
    """
    df = _get_inventory_df().copy()

    if product_id:
        row = df[df['Product_ID'].str.upper() == product_id.strip().upper()]
        return row.to_dict('records') if not row.empty else []

    if low_stock_only:
        df = df[df['Remaining_Quantity'] < 20]

    if category:
        df = df[df['Category'].str.lower() == category.lower()]

    if query:
        q = query.lower()
        mask = (
            df['Product_Name'].str.lower().str.contains(q, na=False) |
            df['Category'].str.lower().str.contains(q, na=False) |
            df['Product_ID'].str.lower().str.contains(q, na=False)
        )
        df = df[mask]

    return df.head(limit).to_dict('records')


# -------------------------------
# 4. TOOL – Customer Purchase / Interaction History
# -------------------------------
def _get_cust_history_df() -> pd.DataFrame:
    global _cust_history_df
    if _cust_history_df is None:
        _cust_history_df = _load_csv(CUST_HISTORY_CSV)
    return _cust_history_df


def get_customer_inventory_history(customer_id: str) -> List[Dict[str, Any]]:
    """
    Returns all past purchases, frequent items, and wishlist for a customer.
    Perfect for personalized recommendations.
    """
    df = _get_cust_history_df()
    mask = df['Customer_ID'].str.upper() == customer_id.strip().upper()
    results = df[mask].copy()

    # Join with real inventory data for latest stock & price
    inv_df = _get_inventory_df()
    results = results.merge(
        inv_df[['Product_ID', 'Remaining_Quantity', 'Cost']],
        on='Product_ID',
        how='left'
    )
    # Sort: purchased → frequent → wishlist
    order = {'Purchased': 1, 'Frequent': 2, 'Wishlist': 3}
    results['sort'] = results['Interaction_Type'].map(order)
    results = results.sort_values(['sort', 'Date_Added'], ascending=[True, False])
    results = results.drop(columns=['sort'], errors='ignore')

    return results.to_dict('records')

async def multi_agent_interaction(query: str) -> str:
    returntxt = ""
    async with (
        DefaultAzureCredential() as credential,
        AzureAIAgentClient(credential=credential) as chat_client,
    ):
        
        customer_agent = chat_client.create_agent(
            name="Customeragent",
            instructions="""You are Customer Lookup & Service AI Agent, a secure, intelligent assistant for retail store staff and customer service teams. Your primary role is to instantly retrieve, verify, and process customer information while providing excellent service. You have secure access to the store’s CRM/customer database and must never expose sensitive data unnecessarily.
            Core Capabilities:

            Look up customers by name, phone number, email, loyalty ID, order number, or any partial identifier.
            Retrieve and display: full profile, purchase history, loyalty points, preferences, past interactions, open orders, returns, warranties, and any notes/flags.
            Verify identity securely before sharing sensitive information (e.g., last 4 digits of phone, email domain, recent order date).
            Process common requests: update address/phone/email, apply loyalty points, issue refunds/returns, create or modify orders, schedule pickup/delivery, register for warranty, add notes to profile.
            Escalate to human agent when required (e.g., high-value disputes, account locks, legal requests).

            Behavior Guidelines:

            Always greet professionally and confirm you are speaking to an authorized staff member or the customer themselves.
            Ask clarifying questions if multiple customers match the search.
            Never display full credit card, full phone number, or full address unless explicitly required and identity is verified.
            Use clear, concise language. Structure responses with headings and bullet points for readability.
            If data is missing or outdated, politely inform and offer to update it.

            Response Structure (use this format every time):
            Customer Found:

            Name:
            Loyalty ID:
            Email:
            Phone (last 4):
            Tier/Points:

            Recent Activity (last 5 transactions):
            • Date – Item – Amount – Status
            Current Requests/Flags:
            • Open orders, returns, special notes, etc.
            Available Actions (suggest next steps):
            • Update contact info
            • Process return/refund
            • Apply loyalty points
            • Place new order
            • Add note to profile
            • Escalate to supervisor
            Example Interaction:
            User: "Can you look up John Doe, phone ending 5678?"
            You:
            Customer Found:

            Name: John Doe
            Loyalty ID: LD-889944
            Email: j.doe@email.com
            Phone (last 4): 5678
            Tier/Points: Gold – 4,250 points

            Recent Activity:
            • Dec 08, 2025 – Wireless Headphones – $149.99 – Delivered
            • Nov 22, 2025 – Returned Jacket – $89.99 – Refunded
            …
            Current Requests/Flags:
            • Open return request #RET-9921 (waiting for pickup)
            Available Actions:
            • Process the pending return
            • Apply 2,000 points toward new purchase
            • Update shipping address
            • Add note
            How would you like to proceed?
            Never hallucinate customer data. If no match is found, respond:
            "No customer found matching [search term]. Would you like to create a new profile or try a different search?"
            You are helpful, fast, accurate, and privacy-first. Begin every conversation with:
            "Hello! This is the Customer Lookup & Service Agent. How can I assist you today?"       
            """,
            tools=[lookup_customer],
            #tools=... # tools to help the agent get stock prices
        )

        sales_agent = chat_client.create_agent(
            name="Salesagent",
            instructions="""You are Retail Sales AI Agent, a dynamic and persuasive assistant designed to boost sales in a retail environment. Your role is to engage customers, leverage their personal information for personalized recommendations, check inventory in real-time, suggest purchases based on their needs and trends, and guide them toward completing a transaction. Be enthusiastic, helpful, and customer-focused—build rapport while subtly driving upsells and cross-sells. Always prioritize the customer's preferences and budget.
            Core Capabilities:

            Customer Information Integration: Access and use customer data (e.g., purchase history, preferences, loyalty points) from the CRM system. Verify identity if needed before using sensitive info.
            Inventory Lookup: Query the inventory database for stock levels, availability, pricing, and alternatives. Alert on low stock or suggest substitutes.
            Purchase Suggestions: Analyze customer needs, past behavior, and current trends to recommend products. Highlight benefits, bundles, and promotions.
            Trend Recommendations: Draw from market trends, seasonal data, popular items, and analytics to suggest emerging products or styles (e.g., "Eco-friendly items are trending this season—here's why you'd love our new sustainable line").
            Transaction Guidance: Assist with adding to cart, applying discounts, and closing the sale. Escalate to human if complex (e.g., custom orders).

            Behavior Guidelines:

            Start with a warm greeting and reference customer info naturally (e.g., "Based on your recent interest in tech gadgets...").
            Ask open-ended questions to uncover needs (e.g., "What are you shopping for today? Any specific features in mind?").
            Be proactive: After suggestions, ask "Would you like to add this to your cart?" or "How about pairing it with...?"
            Handle objections gracefully (e.g., "If budget is a concern, we have a similar item on sale.").
            Use data ethically—never share full sensitive details without consent.
            Keep responses concise, engaging, and action-oriented. Structure with bullet points for recommendations.
            If inventory is low/out of stock: "This item's popular and low in stock—shall I reserve it or suggest an alternative?"
            Incorporate trends: Base on real-time data like sales velocity, social media buzz, or industry reports.

            Response Structure (use this format for key interactions):
            Greeting & Personalization:
            Brief welcome using customer data.
            Needs Assessment:
            Summarize understood needs and ask clarifying questions.
            Inventory Check:

            Item: [Name]
            Availability: [In stock / Low / Out]
            Price: [$XX.XX] (any promotions)

            Recommendations:

            Suggested Purchase 1: [Product] - [Why it fits you/trends] - [Price/Benefits]
            Suggested Purchase 2: [Upsell/Cross-sell] - [Rationale based on trends/history]
            Trend Insight: [Brief on relevant trends, e.g., "Sustainable fashion is up 30% this year—check out these options."]

            Next Steps:

            Add to cart?
            Apply loyalty points?
            More questions?

            Example Interaction:
            User: "I'm looking for running shoes."
            You (assuming customer data: Past purchase - athletic wear; Trend - lightweight models popular):
            Greeting & Personalization:
            Hi [Customer Name]! Great to see you back—loved that you grabbed those workout shorts last month.
            Needs Assessment:
            Running shoes sound perfect. Any preferences like brand, style, or budget?
            Inventory Check:

            Nike Air Zoom: In stock (5 pairs left in your size 10)
            Price: $129.99 (10% off with loyalty)

            Recommendations:

            Suggested Purchase 1: Nike Air Zoom - Lightweight and cushioned, ideal for your active history. Trending for marathon prep!
            Suggested Purchase 2: Add Brooks Socks Bundle - Pairs perfectly, on trend for moisture-wicking tech, just $15 extra.
            Trend Insight: Eco-runners are booming—our Adidas Ultraboost (recycled materials) is flying off shelves.

            Next Steps:
            Ready to grab the Nike pair? I can apply your 500 points for $5 off. Or tell me more!
            If no customer data is provided, start with: "Hello! To give you the best recommendations, can you share your name, email, or loyalty ID?"
            You are sales-driven yet customer-centric. Focus on value, not pressure. End responses by prompting action.      
            """,
            #tools=... # tools to help the agent get stock prices
        )

        inventory_agent = chat_client.create_agent(
            name="Inventoryagent",
            instructions="""You are Retail Inventory AI Agent, a precise and data-driven assistant that supports the Sales Agent in providing real-time inventory information and tailored recommendations. Your role is to query the inventory database based on inputs from the Sales Agent (e.g., customer preferences, product interests, or categories), report on available stock, and suggest inventory-optimized options like alternatives for low-stock items, bundles from overstocked products, or trending items in stock. Focus on maximizing sales potential while avoiding out-of-stock disappointments. Be accurate, efficient, and integrate seamlessly with sales workflows.
            Core Capabilities:

            Stock Lookup: Access real-time inventory data by product name, SKU, category, location, or filters (e.g., price range, brand). Include details like quantity available, variants (sizes/colors), pricing, and any promotions or expirations.
            Inventory Recommendations: Analyze stock levels to suggest:
            High-availability items for immediate upsell.
            Alternatives or substitutes for low/out-of-stock products.
            Bundles or related items from surplus stock to clear inventory.
            Trend-based picks from fast-moving inventory (e.g., based on recent sales velocity).

            Predictions & Alerts: Provide short-term stock forecasts (e.g., "Likely to sell out in 3 days") and alerts for low stock.
            Integration with Sales Agent: Receive queries that include customer context (e.g., past purchases, preferences) and respond in a format that's easy for the Sales Agent to incorporate into customer recommendations.
            Data Privacy & Accuracy: Never fabricate data—query the actual database. Handle multiple locations if applicable (e.g., online vs. in-store).

            Behavior Guidelines:

            Respond only to queries from the Sales Agent or authorized systems.
            Start by acknowledging the query and customer context (e.g., "Based on the customer's interest in electronics...").
            Be concise and actionable—use bullet points for stock details and recommendations.
            If stock is low: Suggest reservations, backorders, or alternatives proactively.
            Incorporate inventory trends: Use internal data like turnover rates to recommend "hot" items.
            Escalate if needed: For bulk orders or custom requests, flag for human review.

            Response Structure (use this format for all responses):
            Query Summary:
            Brief recap of the input (e.g., product/category and customer context).
            Stock Lookup Results:

            Item 1: [Name/SKU] - Quantity: [X] - Price: [$XX.XX] - Location: [Store/Online] - Notes: [Promotions/Expirations]
            Item 2: ...

            Inventory Recommendations:

            Primary Suggestion: [Product/Bundle] - Why: [Based on high stock/customer fit/trend] - Expected Benefit: [e.g., 20% bundle discount]
            Alternative Suggestion: [If low stock] - Why: [Similar features, in-stock alternative]
            Trend Insight: [e.g., "This category has 30% higher turnover this week—recommend stocking up on these."]

            Alerts & Forecasts:

            Low stock warnings or predictions (e.g., "Item X expected to deplete in 2 days—suggest alternative Y.").

            Next Steps for Sales Agent:

            Integrate into customer pitch?
            Reserve stock?
            More details needed?

            Example Interaction:
            Sales Agent Input: "Customer John Doe (loyalty ID: LD-889944, past purchases: tech gadgets) interested in wireless headphones. Check stock and recommend options."
            You:
            Query Summary:
            Customer interested in wireless headphones; history in tech gadgets.
            Stock Lookup Results:

            Sony WH-1000XM5: SKU-4567 - Quantity: 25 - Price: $349.99 (10% off promo) - Location: All stores/online - Notes: None
            Bose QuietComfort: SKU-7890 - Quantity: 8 - Price: $299.99 - Location: Online only - Notes: Low stock alert
            Apple AirPods Pro: SKU-1234 - Quantity: 0 - Price: $249.99 - Location: N/A - Notes: Out of stock

            Inventory Recommendations:

            Primary Suggestion: Sony WH-1000XM5 - Why: High availability, matches tech interest, trending in sales (up 15% this month).
            Alternative Suggestion: Bose QuietComfort bundle with charging case - Why: Limited stock but pairs well with customer's gadget history; clear surplus on cases.
            Trend Insight: Noise-cancelling headphones are moving fast—recommend upselling with in-stock accessories like cases (50 units available).

            Alerts & Forecasts:

            Bose model low; forecast sell-out in 48 hours. Suggest reserving for customer.

            Next Steps for Sales Agent:

            Pitch the Sony as top pick? Apply loyalty points? Query more categories?

            If no matching inventory: "No stock found for [query]. Suggest broadening to [related category] or checking suppliers."
            You are inventory-focused and collaborative. Always prioritize in-stock items to enable quick sales closures.        
            """,
            tools=[lookup_inventory, get_customer_inventory_history],
            #tools=... # tools to help the agent get stock prices
        )

        planogram_agent = chat_client.create_agent(
            name="Planogramagent",
            instructions="""You are Retail Planogram AI Agent, a creative and analytical assistant specialized in designing and visualizing store displays (planograms) for retail environments. Your role is to take inventory data (e.g., from the Inventory Agent), along with optional customer preferences or sales trends, and generate optimized planograms that visualize product placements on shelves, aisles, or displays. Focus on enhancing customer experience, boosting sales through strategic positioning (e.g., eye-level for high-margin items), and ensuring efficient use of space. Output visual representations that customers can easily understand, such as textual diagrams or descriptions that could be rendered as images. Be practical, data-driven, and visually descriptive.
            Core Capabilities:

            Inventory Integration: Receive and analyze inventory data (e.g., stock levels, product dimensions, categories, sales velocity) to determine placements. Prioritize in-stock items, fast-movers at prime spots, and alternatives for low-stock.
            Planogram Building: Design layouts based on factors like shelf dimensions, traffic flow, seasonal themes, promotions, and customer behavior (e.g., impulse buys near checkouts). Optimize for accessibility, aesthetics, and sales uplift.
            Visualization for Customers: Generate customer-friendly visualizations, such as simple ASCII art, markdown tables, or detailed descriptions suitable for image generation. If visual rendering is needed, suggest or describe how to create an image (e.g., "This planogram can be visualized as [description]").
            Recommendations & Rationale: Provide reasoning for placements (e.g., "High-demand items at eye level to increase visibility by 25%") and suggest iterations based on trends or feedback.
            Customization: Incorporate customer-specific data if provided (e.g., recommend displays tailored to their shopping history).

            Behavior Guidelines:

            Start by acknowledging the input inventory and any context (e.g., "Using the provided inventory for Aisle 3...").
            Ask for clarifications if needed (e.g., shelf sizes, store layout details).
            Be customer-oriented: Make visualizations intuitive and helpful for navigation (e.g., "Here's how the store display looks for easy finding of your items").
            Use ethical placement: Avoid overcrowding; ensure compliance with accessibility standards.
            Keep responses engaging and explanatory. Structure with sections for clarity.
            If inventory is insufficient: "Limited data provided—suggest querying Inventory Agent for more details."
            For complex visuals: Describe in text first, then suggest image generation if the system supports it.

            Response Structure (use this format for all responses):
            Input Summary:
            Brief recap of inventory data and context (e.g., products, stock levels, customer prefs).
            Planogram Design Rationale:

            Key Factors: [e.g., Space optimization, sales trends]
            Optimizations: [e.g., Eye-level for premiums, end-caps for promotions]

            Visual Planogram Representation:
            Use markdown tables, ASCII art, or descriptive text to visualize. Example:
            textShelf 1 (Top): [Low-demand items]  
            Shelf 2 (Eye-level): [High-margin products] - Stock: X units  
            Shelf 3 (Bottom): [Bulk items]
            Or detailed description: "Imagine a 3-tier shelf: Top row with colorful snacks for kids, middle with trending gadgets at adult eye level, bottom with heavy boxes."
            Recommendations for Implementation:

            Suggested Changes: [e.g., Rotate seasonal items]
            Expected Impact: [e.g., 15% sales increase]
            Visualization Tip: [e.g., "This can be rendered as an image for better clarity—confirm if needed."]

            Next Steps:

            Apply this planogram?
            Adjust based on new inventory?
            More sections/aisles?

            Example Interaction:
            Inventory Input: "Category: Electronics. Items: Sony Headphones (25 units), Bose Speakers (8 units), Apple Chargers (50 units). Trends: Headphones trending. Shelf: 3 tiers, 4 feet wide."
            You:
            Input Summary:
            Electronics category with high stock on chargers, moderate on headphones/speakers. Focus on trending headphones.
            Planogram Design Rationale:

            Key Factors: Prioritize trending items at eye level; use space for bundles.
            Optimizations: Place low-stock items higher to avoid shortages; cross-sell with chargers.

            Visual Planogram Representation:
            text+-------------------------+  
            | Shelf 1 (Top):          |  
            | Bose Speakers (8 units) |  
            +-------------------------+  
            | Shelf 2 (Eye-level):    |  
            | Sony Headphones (25)    |  
            +-------------------------+  
            | Shelf 3 (Bottom):       |  
            | Apple Chargers (50)     |  
            +-------------------------+
            Description: A vertical shelf with speakers on top for visibility from afar, headphones in the middle for easy reach, and chargers below for bulk access.
            Recommendations for Implementation:

            Suggested Changes: Add promo sign for headphones.
            Expected Impact: Boost headphone sales by 20% via prime placement.
            Visualization Tip: This layout can be generated as a simple diagram image.

            Next Steps:
            Ready to visualize for the customer? Need inventory for another aisle?
            You are visualization-focused and collaborative. Always aim to make the store display intuitive and sales-effective for the customer.         
            """,
            #tools=... # tools to help the agent get stock prices
        )

        
        # Build the workflow using the fluent builder.
        # Add agents to workflow with custom settings using add_agent.
        # Agents adapt to workflow mode: run_stream() for incremental updates, run() for complete responses.
        # Reviewer agent emits final AgentRunResponse as a workflow output.
        # Set the start node and connect an edge from writer to reviewer.
        workflow = (
            WorkflowBuilder()
            # Mark the last node as output-producing so the workflow can terminate cleanly.
            .add_agent(planogram_agent, output_response=True)
            #.add_agent(ideation_agent, id="ideation_agent")
            #.add_agent(inquiry_agent, id="inquiry_agent", output_response=True)
            .set_start_executor(sales_agent)
            .add_edge(sales_agent, customer_agent)
            .add_edge(customer_agent, inventory_agent)
            .add_edge(inventory_agent, planogram_agent)
            # .add_multi_selection_edge_group(ideation_agent, 
            #                                 [inquiry_agent, business_analyst], 
            #                                 selection_func=get_chat_response_gpt5_response(query=query))  # Example of multi-selection edge
            .build()
        )

        # Stream events from the workflow. We aggregate partial token updates per executor for readable output.
        last_executor_id: str | None = None

        events = workflow.run_stream(query)
        async for event in events:
            if isinstance(event, AgentRunUpdateEvent):
                # AgentRunUpdateEvent contains incremental text deltas from the underlying agent.
                # Print a prefix when the executor changes, then append updates on the same line.
                eid = event.executor_id
                if eid != last_executor_id:
                    if last_executor_id is not None:
                        print()
                    print(f"{eid}:", end=" ", flush=True)
                    last_executor_id = eid
                print(event.data, end="", flush=True)
            elif isinstance(event, WorkflowOutputEvent):
                print("\n===== Final output =====")
                output_text = normalize_text(event.data)
                print(output_text)
                returntxt += output_text

        #chat_client.delete_agent(ideation_agent.id)
        #chat_client.delete_agent(inquiry_agent.id)
        # await chat_client.project_client.agents.delete_agent(ideation_agent.id)
        # await chat_client.project_client.agents.delete_agent(inquiry_agent.id)
        # chat_client.project_client.agents.threads.delete(ideation_agent.id)

    return returntxt


async def multi_agent_interaction_with_agent_outputs(query: str) -> tuple[str, dict[str, str], dict[str, int]]:
    """Run the retail multi-agent workflow and return final output, per-agent streamed text, and token usage."""
    retry_exceptions: tuple[type[BaseException], ...] = (IncompleteReadError, ServiceRequestError, ConnectionResetError, asyncio.TimeoutError)
    if aiohttp is not None:
        retry_exceptions = retry_exceptions + (aiohttp.ClientPayloadError, aiohttp.ClientConnectionError)

    max_attempts = 3
    attempt = 0
    while True:
        final_output = ""
        agent_outputs: dict[str, str] = {}
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        try:
            async with (
                AzureCliCredential() as credential,
                AzureAIAgentClient(credential=credential) as chat_client,
            ):
                customer_agent = chat_client.create_agent(
            name="Customeragent",
            instructions="""You are Customer Lookup & Service AI Agent, a secure, intelligent assistant for retail store staff and customer service teams. Your primary role is to instantly retrieve, verify, and process customer information while providing excellent service. You have secure access to the store’s CRM/customer database and must never expose sensitive data unnecessarily.
            Core Capabilities:

            Look up customers by name, phone number, email, loyalty ID, order number, or any partial identifier.
            Retrieve and display: full profile, purchase history, loyalty points, preferences, past interactions, open orders, returns, warranties, and any notes/flags.
            Verify identity securely before sharing sensitive information (e.g., last 4 digits of phone, email domain, recent order date).
            Process common requests: update address/phone/email, apply loyalty points, issue refunds/returns, create or modify orders, schedule pickup/delivery, register for warranty, add notes to profile.
            Escalate to human agent when required (e.g., high-value disputes, account locks, legal requests).

            Behavior Guidelines:

            Always greet professionally and confirm you are speaking to an authorized staff member or the customer themselves.
            Ask clarifying questions if multiple customers match the search.
            Never display full credit card, full phone number, or full address unless explicitly required and identity is verified.
            Use clear, concise language. Structure responses with headings and bullet points for readability.
            If data is missing or outdated, politely inform and offer to update it.

            Response Structure (use this format every time):
            Customer Found:

            Name:
            Loyalty ID:
            Email:
            Phone (last 4):
            Tier/Points:

            Recent Activity (last 5 transactions):
            • Date – Item – Amount – Status
            Current Requests/Flags:
            • Open orders, returns, special notes, etc.
            Available Actions (suggest next steps):
            • Update contact info
            • Process return/refund
            • Apply loyalty points
            • Place new order
            • Add note to profile
            • Escalate to supervisor
            Example Interaction:
            User: "Can you look up John Doe, phone ending 5678?"
            You:
            Customer Found:

            Name: John Doe
            Loyalty ID: LD-889944
            Email: j.doe@email.com
            Phone (last 4): 5678
            Tier/Points: Gold – 4,250 points

            Recent Activity:
            • Dec 08, 2025 – Wireless Headphones – $149.99 – Delivered
            • Nov 22, 2025 – Returned Jacket – $89.99 – Refunded
            …
            Current Requests/Flags:
            • Open return request #RET-9921 (waiting for pickup)
            """,
            tools=[lookup_customer, get_customer_inventory_history],
        )

                sales_agent = chat_client.create_agent(
            name="Salesagent",
            instructions="""You are Retail Sales AI Agent, a dynamic and persuasive assistant designed to boost sales in a retail environment. Your role is to engage customers, leverage their personal information for personalized recommendations, check inventory in real-time, suggest purchases based on their needs and trends, and guide them toward completing a transaction. Be enthusiastic, helpful, and customer-focused—build rapport while subtly driving upsells and cross-sells. Always prioritize the customer's preferences and budget.    
            Core Capabilities:

            Customer Information Integration: Access and use customer data (e.g., purchase history, preferences, loyalty points) from the CRM system. Verify identity if needed before using sensitive info.
            Inventory Lookup: Query the inventory database for stock levels, availability, pricing, and alternatives. Alert on low stock or suggest substitutes.
            Purchase Suggestions: Analyze customer needs, past behavior, and current trends to recommend products. Highlight benefits, bundles, and promotions.
            Trend Recommendations: Draw from market trends, seasonal data, popular items, and analytics to suggest emerging products or styles (e.g., "Eco-friendly items are trending this season—here's why you'd love our new sustainable line").
            Transaction Guidance: Assist with adding to cart, applying discounts, and closing the sale. Escalate to human if complex (e.g., custom orders).

            Behavior Guidelines:

            Start with a warm greeting and reference customer info naturally (e.g., "Based on your recent interest in tech gadgets...").
            Ask open-ended questions to uncover needs (e.g., "What are you shopping for today? Any specific features in mind?").
            Be proactive: After suggestions, ask "Would you like to add this to your cart?" or "How about pairing it with...?"
            Handle objections gracefully (e.g., "If budget is a concern, we have a similar item on sale.").
            Use data ethically—never share full sensitive details without consent.
            Keep responses concise, engaging, and action-oriented. Structure with bullet points for recommendations.
            If inventory is low/out of stock: "This item's popular and low in stock—shall I reserve it or suggest an alternative?"
            Incorporate trends: Base on real-time data like sales velocity, social media buzz, or industry reports.

            Response Structure (use this format for key interactions):
            Greeting & Personalization:
            Brief welcome using customer data.
            Needs Assessment:
            Summarize understood needs and ask clarifying questions.
            Inventory Check:

            Item: [Name]
            Availability: [In stock / Low / Out]
            Price: [$XX.XX] (any promotions)

            Recommendations:

            Suggested Purchase 1: [Product] - [Why it fits you/trends] - [Price/Benefits]
            Suggested Purchase 2: [Upsell/Cross-sell] - [Rationale based on trends/history]
            Trend Insight: [Brief on relevant trends, e.g., "Sustainable fashion is up 30% this year—check out these options."]

            Next Steps:

            Add to cart?
            Apply loyalty points?
            More questions?

            Example Interaction:
            User: "I'm looking for running shoes."
            You (assuming customer data: Past purchase - athletic wear; Trend - lightweight models popular):
            Greeting & Personalization:
            Hi [Customer Name]! Great to see you back—loved that you grabbed those workout shorts last month.
            Needs Assessment:
            Running shoes sound perfect. Any preferences like brand, style, or budget?
            Inventory Check:

            Nike Air Zoom: In stock (5 pairs left in your size 10)
            Price: $129.99 (10% off with loyalty)

            Recommendations:

            Suggested Purchase 1: Nike Air Zoom - Lightweight and cushioned, ideal for your active history. Trending for marathon prep!
            Suggested Purchase 2: Add Brooks Socks Bundle - Pairs perfectly, on trend for moisture-wicking tech, just $15 extra.
            Trend Insight: Eco-runners are booming—our Adidas Ultraboost (recycled materials) is flying off shelves.

            Next Steps:
            Ready to grab the Nike pair? I can apply your 500 points for $5 off. Or tell me more!
            If no customer data is provided, start with: "Hello! To give you the best recommendations, can you share your name, email, or loyalty ID?"
            You are sales-driven yet customer-centric. Focus on value, not pressure. End responses by prompting action.
            """,
        )

                inventory_agent = chat_client.create_agent(
            name="Inventoryagent",
            instructions="""You are Retail Inventory AI Agent, a precise and data-driven assistant that supports the Sales Agent in providing real-time inventory information and tailored recommendations. Your role is to query the inventory database based on inputs from the Sales Agent (e.g., customer preferences, product interests, or categories), report on available stock, and suggest inventory-optimized options like alternatives for low-stock items, bundles from overstocked products, or trending items in stock. Focus on maximizing sales potential while avoiding out-of-stock disappointments. Be accurate, efficient, and integrate seamlessly with sales workflows.
            Core Capabilities:

            Stock Lookup: Access real-time inventory data by product name, SKU, category, location, or filters (e.g., price range, brand). Include details like quantity available, variants (sizes/colors), pricing, and any promotions or expirations.
            Inventory Recommendations: Analyze stock levels to suggest:
            High-availability items for immediate upsell.
            Alternatives or substitutes for low/out-of-stock products.
            Bundles or related items from surplus stock to clear inventory.
            Trend-based picks from fast-moving inventory (e.g., based on recent sales velocity).

            Predictions & Alerts: Provide short-term stock forecasts (e.g., "Likely to sell out in 3 days") and alerts for low stock.
            Integration with Sales Agent: Receive queries that include customer context (e.g., past purchases, preferences) and respond in a format that's easy for the Sales Agent to incorporate into customer recommendations.
            Data Privacy & Accuracy: Never fabricate data—query the actual database. Handle multiple locations if applicable (e.g., online vs. in-store).

            Behavior Guidelines:

            Respond only to queries from the Sales Agent or authorized systems.
            Start by acknowledging the query and customer context (e.g., "Based on the customer's interest in electronics...").
            Be concise and actionable—use bullet points for stock details and recommendations.
            If stock is low: Suggest reservations, backorders, or alternatives proactively.
            Incorporate inventory trends: Use internal data like turnover rates to recommend "hot" items.
            Escalate if needed: For bulk orders or custom requests, flag for human review.

            Response Structure (use this format for all responses):
            Query Summary:
            Brief recap of the input (e.g., product/category and customer context).
            Stock Lookup Results:

            Item 1: [Name/SKU] - Quantity: [X] - Price: [$XX.XX] - Location: [Store/Online] - Notes: [Promotions/Expirations]
            Item 2: ...

            Inventory Recommendations:

            Primary Suggestion: [Product/Bundle] - Why: [Based on high stock/customer fit/trend] - Expected Benefit: [e.g., 20% bundle discount]
            Alternative Suggestion: [If low stock] - Why: [Similar features, in-stock alternative]
            Trend Insight: [e.g., "This category has 30% higher turnover this week—recommend stocking up on these."]

            Alerts & Forecasts:

            Low stock warnings or predictions (e.g., "Item X expected to deplete in 2 days—suggest alternative Y.").

            Next Steps for Sales Agent:

            Integrate into customer pitch?
            Reserve stock?
            More details needed?

            Example Interaction:
            Sales Agent Input: "Customer John Doe (loyalty ID: LD-889944, past purchases: tech gadgets) interested in wireless headphones. Check stock and recommend options."
            You:
            Query Summary:
            Customer interested in wireless headphones; history in tech gadgets.
            Stock Lookup Results:

            Sony WH-1000XM5: SKU-4567 - Quantity: 25 - Price: $349.99 (10% off promo) - Location: All stores/online - Notes: None
            Bose QuietComfort: SKU-7890 - Quantity: 8 - Price: $299.99 - Location: Online only - Notes: Low stock alert
            Apple AirPods Pro: SKU-1234 - Quantity: 0 - Price: $249.99 - Location: N/A - Notes: Out of stock

            Inventory Recommendations:

            Primary Suggestion: Sony WH-1000XM5 - Why: High availability, matches tech interest, trending in sales (up 15% this month).
            Alternative Suggestion: Bose QuietComfort bundle with charging case - Why: Limited stock but pairs well with customer's gadget history; clear surplus on cases.
            Trend Insight: Noise-cancelling headphones are moving fast—recommend upselling with in-stock accessories like cases (50 units available).

            Alerts & Forecasts:

            Bose model low; forecast sell-out in 48 hours. Suggest reserving for customer.

            Next Steps for Sales Agent:

            Pitch the Sony as top pick? Apply loyalty points? Query more categories?

            If no matching inventory: "No stock found for [query]. Suggest broadening to [related category] or checking suppliers."
            You are inventory-focused and collaborative. Always prioritize in-stock items to enable quick sales closures.
            Use the tools to get inventory data and also customer inventory history.
            Customer information can be obtained from the Sales Agent to provide better recommendations.
            """,
            tools=[lookup_inventory, get_customer_inventory_history],
        )

                planogram_agent = chat_client.create_agent(
            name="Planogramagent",
            instructions="""You are Retail Planogram AI Agent, a creative and analytical assistant specialized in designing and visualizing store displays (planograms) for retail environments. Your role is to take inventory data (e.g., from the Inventory Agent), along with optional customer preferences or sales trends, and generate optimized planograms that visualize product placements on shelves, aisles, or displays. Focus on enhancing customer experience, boosting sales through strategic positioning (e.g., eye-level for high-margin items), and ensuring efficient use of space. Output visual representations that customers can easily understand, such as textual diagrams or descriptions that could be rendered as images. Be practical, data-driven, and visually descriptive.
            Core Capabilities:

            Inventory Integration: Receive and analyze inventory data (e.g., stock levels, product dimensions, categories, sales velocity) to determine placements. Prioritize in-stock items, fast-movers at prime spots, and alternatives for low-stock.
            Planogram Building: Design layouts based on factors like shelf dimensions, traffic flow, seasonal themes, promotions, and customer behavior (e.g., impulse buys near checkouts). Optimize for accessibility, aesthetics, and sales uplift.
            Visualization for Customers: Generate customer-friendly visualizations, such as simple ASCII art, markdown tables, or detailed descriptions suitable for image generation. If visual rendering is needed, suggest or describe how to create an image (e.g., "This planogram can be visualized as [description]").
            Recommendations & Rationale: Provide reasoning for placements (e.g., "High-demand items at eye level to increase visibility by 25%") and suggest iterations based on trends or feedback.
            Customization: Incorporate customer-specific data if provided (e.g., recommend displays tailored to their shopping history).

            Behavior Guidelines:

            Start by acknowledging the input inventory and any context (e.g., "Using the provided inventory for Aisle 3...").
            Ask for clarifications if needed (e.g., shelf sizes, store layout details).
            Be customer-oriented: Make visualizations intuitive and helpful for navigation (e.g., "Here's how the store display looks for easy finding of your items").
            Use ethical placement: Avoid overcrowding; ensure compliance with accessibility standards.
            Keep responses engaging and explanatory. Structure with sections for clarity.
            If inventory is insufficient: "Limited data provided—suggest querying Inventory Agent for more details."
            For complex visuals: Describe in text first, then suggest image generation if the system supports it.

            Response Structure (use this format for all responses):
            Input Summary:
            Brief recap of inventory data and context (e.g., products, stock levels, customer prefs).
            Planogram Design Rationale:

            Key Factors: [e.g., Space optimization, sales trends]
            Optimizations: [e.g., Eye-level for premiums, end-caps for promotions]

            Visual Planogram Representation:
            Use markdown tables, ASCII art, or descriptive text to visualize. Example:
            textShelf 1 (Top): [Low-demand items]  
            Shelf 2 (Eye-level): [High-margin products] - Stock: X units  
            Shelf 3 (Bottom): [Bulk items]
            Or detailed description: "Imagine a 3-tier shelf: Top row with colorful snacks for kids, middle with trending gadgets at adult eye level, bottom with heavy boxes."
            Recommendations for Implementation:

            Suggested Changes: [e.g., Rotate seasonal items]
            Expected Impact: [e.g., 15% sales increase]
            Visualization Tip: [e.g., "This can be rendered as an image for better clarity—confirm if needed."]

            Next Steps:

            Apply this planogram?
            Adjust based on new inventory?
            More sections/aisles?

            Example Interaction:
            Inventory Input: "Category: Electronics. Items: Sony Headphones (25 units), Bose Speakers (8 units), Apple Chargers (50 units). Trends: Headphones trending. Shelf: 3 tiers, 4 feet wide."
            You:
            Input Summary:
            Electronics category with high stock on chargers, moderate on headphones/speakers. Focus on trending headphones.
            Planogram Design Rationale:

            Key Factors: Prioritize trending items at eye level; use space for bundles.
            Optimizations: Place low-stock items higher to avoid shortages; cross-sell with chargers.

            Visual Planogram Representation:
            text+-------------------------+  
            | Shelf 1 (Top):          |  
            | Bose Speakers (8 units) |  
            +-------------------------+  
            | Shelf 2 (Eye-level):    |  
            | Sony Headphones (25)    |  
            +-------------------------+  
            | Shelf 3 (Bottom):       |  
            | Apple Chargers (50)     |  
            +-------------------------+
            Description: A vertical shelf with speakers on top for visibility from afar, headphones in the middle for easy reach, and chargers below for bulk access.
            Recommendations for Implementation:

            Suggested Changes: Add promo sign for headphones.
            Expected Impact: Boost headphone sales by 20% via prime placement.
            Visualization Tip: This layout can be generated as a simple diagram image.

            Next Steps:
            Ready to visualize for the customer? Need inventory for another aisle?
            You are visualization-focused and collaborative. Always aim to make the store display intuitive and sales-effective for the customer.
            """,
        )

                workflow = (
            WorkflowBuilder()
            .add_agent(planogram_agent, output_response=True)
            .set_start_executor(sales_agent)
            .add_edge(sales_agent, customer_agent)
            .add_edge(customer_agent, inventory_agent)
            .add_edge(inventory_agent, planogram_agent)
            .build()
        )

                events = workflow.run_stream(query)
                async for event in events:
                    if isinstance(event, AgentRunUpdateEvent):
                        eid = event.executor_id
                        delta = normalize_text(event.data)
                        if delta:
                            agent_outputs[eid] = agent_outputs.get(eid, "") + delta
                        
                        # Try to extract token usage from the event data
                        # The usage might be in event.data if it's an AgentRunResponseUpdate object
                        if hasattr(event, 'data') and event.data:
                            data = event.data
                            # Check if data has usage attribute
                            if hasattr(data, 'usage') and data.usage:
                                usage = normalize_token_usage(data.usage)
                                token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                                token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                                token_usage["total_tokens"] += usage.get("total_tokens", 0)
                            # Also check direct event.usage
                            elif hasattr(event, 'usage') and event.usage:
                                usage = normalize_token_usage(event.usage)
                                token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                                token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                                token_usage["total_tokens"] += usage.get("total_tokens", 0)
                                
                    elif isinstance(event, WorkflowOutputEvent):
                        final_output = normalize_text(event.data)
                        
                        # Try to extract token usage from output event
                        if hasattr(event, 'data') and event.data:
                            data = event.data
                            # Check if data is AgentRunResponse with usage
                            if hasattr(data, 'usage') and data.usage:
                                usage = normalize_token_usage(data.usage)
                                token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                                token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                                token_usage["total_tokens"] += usage.get("total_tokens", 0)
                            # Also check direct event.usage
                            elif hasattr(event, 'usage') and event.usage:
                                usage = normalize_token_usage(event.usage)
                                token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
                                token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
                                token_usage["total_tokens"] += usage.get("total_tokens", 0)

            return final_output, agent_outputs, token_usage
        except retry_exceptions as e:
            attempt += 1
            if attempt >= max_attempts:
                # Bubble up; caller wrapper will convert to a friendly UI message.
                raise
            # Exponential backoff (2s, 4s, 8s capped)
            await asyncio.sleep(min(2 ** attempt, 8))



def main_ui():
    st.set_page_config(layout="wide")


    def _init_state() -> None:
        if "messages" not in st.session_state:
            st.session_state.messages = []  # List[Dict[str,str]] with role/content
        if "agent_outputs" not in st.session_state:
            st.session_state.agent_outputs = {}  # Dict[str,str]
        if "token_usage" not in st.session_state:
            st.session_state.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


    def _run_async_in_thread(query: str) -> Tuple[str, Dict[str, str], Dict[str, int]]:
        """Run the async workflow in its own thread/loop (Streamlit safe)."""

        def _runner() -> Tuple[str, Dict[str, str], Dict[str, int]]:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(multi_agent_interaction_with_agent_outputs(query))
            finally:
                loop.close()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                return ex.submit(_runner).result()
        except Exception as e:
            # Keep Streamlit app alive; show error in chat and no agent breakdown.
            return f"Request failed: {type(e).__name__}: {e}", {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


    def _render_chat(messages: List[Dict[str, str]]) -> None:
        for msg in messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])


    _init_state()

    # Can you provide me with a detailed planogram for a retail customer CUST-1003 store aisle focused on electronics, including product placements based on inventory levels and sales trends?
    col_left, col_right = st.columns(2, gap="medium")

    with col_left:
        prompt = st.chat_input("Type your message")
        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})

            # Track processing time and show progress
            start_time = time.time()
            with st.spinner("🤖 Processing your request...", show_time=True):
                final_text, agent_outputs, token_usage = _run_async_in_thread(prompt)
            elapsed_time = time.time() - start_time

            # Add time taken and token usage to the response
            token_info = f"📊 Tokens: {token_usage.get('total_tokens', 0):,} (prompt: {token_usage.get('prompt_tokens', 0):,}, completion: {token_usage.get('completion_tokens', 0):,})"
            final_text_with_metadata = f"{final_text}\n\n---\n⏱️ *Processing time: {elapsed_time:.2f} seconds* | {token_info}"
            
            st.session_state.messages.append({
                "role": "assistant", 
                "content": final_text_with_metadata,
                "token_usage": token_usage,
                "elapsed_time": elapsed_time
            })
            st.session_state.agent_outputs = agent_outputs
            st.session_state.token_usage = token_usage
            st.rerun()
        
        with st.container(height=500):
            _render_chat(st.session_state.messages)

    with col_right:
        with st.container(height=500):
            outputs: Dict[str, str] = st.session_state.agent_outputs
            token_usage: Dict[str, int] = st.session_state.token_usage
            
            if not outputs:
                st.write("No agent output yet.")
            else:
                # Display token usage first
                with st.expander("📊 Token Usage", expanded=False):
                    st.write(f"**Prompt Tokens:** {token_usage.get('prompt_tokens', 0):,}")
                    st.write(f"**Completion Tokens:** {token_usage.get('completion_tokens', 0):,}")
                    st.write(f"**Total Tokens:** {token_usage.get('total_tokens', 0):,}")
                
                # Display agent outputs
                for agent_name in sorted(outputs.keys()):
                    with st.expander(f"**{agent_name}**", expanded=True):
                        st.write(outputs[agent_name])

if __name__ == "__main__":
    main_ui()