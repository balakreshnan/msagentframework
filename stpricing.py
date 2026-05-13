# Copyright (c) Microsoft. All rights reserved.
"""
Microsoft Foundry Pricing & Advisory Chat (Streamlit + Agent Framework)

Single-screen UI:
  - st.chat_input pinned at the bottom
  - Two columns (medium gap):
      LEFT  : token usage + Microsoft Foundry cost estimate inside st.expander(s)
      RIGHT : conversation history inside an st.container(height=500)

Topics the agent answers:
  - Microsoft Foundry agent usage
  - Model token usage
  - Knowledge & tools (RAG, file search, function tools, MCP)
  - Observability & trust (App Insights, evaluations, content safety)

The agent uses Microsoft Agent Framework with AzureOpenAIChatClient and exposes
two tools that compute cost for an agentic AI application running on Foundry.
"""

from __future__ import annotations

import csv
import io
import json
import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

load_dotenv()

# ----------------------------------------------------------------------------
# Page setup — keep things tight so it fits on one screen without scrolling.
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Foundry Pricing Advisor",
    page_icon="💸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      /* Compact layout to fit one screen */
      .block-container {padding-top: 0.8rem; padding-bottom: 0.4rem; max-width: 100%;}
      header[data-testid="stHeader"] {height: 0; visibility: hidden;}
      footer {visibility: hidden;}
      .app-title {font-size: 1.15rem; font-weight: 700; margin: 0 0 0.25rem 0;}
      .app-sub   {font-size: 0.80rem; color: #6b7280; margin: 0 0 0.5rem 0;}
      div[data-testid="stChatMessage"] {padding: 0.35rem 0.55rem; margin-bottom: 0.25rem;}
      .stExpander {border-radius: 8px;}
      .small-note {font-size: 0.75rem; color: #6b7280;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------------------------------------------------------
# Microsoft Foundry / Azure OpenAI public list pricing (USD / 1K tokens).
# Values are reasonable defaults used for *estimation only* — adjust to your
# committed pricing as needed. Keep this table in one place so the tools can
# reference it deterministically.
# ----------------------------------------------------------------------------
FOUNDRY_PRICING_PER_1K: dict[str, dict[str, float]] = {
    # model name              input        output
    "gpt-4o":                 {"input": 0.0025, "output": 0.0100},
    "gpt-4o-mini":            {"input": 0.00015, "output": 0.0006},
    "gpt-4.1":                {"input": 0.0020, "output": 0.0080},
    "gpt-4.1-mini":           {"input": 0.0004, "output": 0.0016},
    "gpt-4.1-nano":           {"input": 0.0001, "output": 0.0004},
    "gpt-5":                  {"input": 0.0050, "output": 0.0150},
    "gpt-5-chat":             {"input": 0.0050, "output": 0.0150},
    "gpt-5-mini":             {"input": 0.0010, "output": 0.0030},
    "gpt-5.4-mini":           {"input": 0.0010, "output": 0.0030},
    "o1":                     {"input": 0.0150, "output": 0.0600},
    "o3-mini":                {"input": 0.0011, "output": 0.0044},
}

EXTRA_FOUNDRY_FEES = {
    # ── Agent Execution (hosted agents) ──
    "agent_vcpu_per_hour":             0.0994, # vCPU per hour
    "agent_memory_gib_per_hour":       0.0118, # Memory GiB per hour
    "thread_storage_per_gb_month":     0.10,   # thread/message storage
    # ── Knowledge & Tools ──
    "file_search_storage_per_gb_day":  0.11,   # file search vector storage $/GB/day (1 GB free)
    "code_interpreter_per_session":    0.033,  # per code interpreter session
    "web_search_per_1k_txn":           14.0,   # Bing web search $/1K transactions
    "custom_search_per_1k_txn":        14.0,   # custom search $/1K transactions
    "function_tool_per_1k_invocations": 0.0,   # no extra charge beyond token cost
    "mcp_tool_per_1k_invocations":     0.0,    # MCP tools—token cost only
    "azure_ai_search_basic_monthly":   75.0,   # dedicated AI Search index
    "vector_store_per_gb_day":         0.10,   # Foundry vector store
    # ── Foundry IQ (Azure AI Search + agentic reasoning) ──
    "foundry_iq_search_basic_monthly": 75.0,    # AI Search Basic tier
    "foundry_iq_search_s1_monthly":    250.0,   # AI Search S1 tier
    "foundry_iq_search_s2_monthly":    1000.0,  # AI Search S2 tier
    "foundry_iq_reasoning_per_1k":     2.50,    # agentic reasoning on top of search
    "foundry_iq_retrieval_low_per_1m":  0.022,   # low / minimal reasoning $/1M retrieval tokens
    "foundry_iq_retrieval_med_per_1m":  0.10,    # medium reasoning $/1M retrieval tokens
    # ── Observability & Trust ──
    "app_insights_per_gb":             2.30,   # telemetry ingestion
    "content_safety_per_1k_calls":     1.00,   # Azure AI Content Safety
    "realtime_eval_per_1k_runs":       1.00,   # realtime eval (runs per agent execution)
    "batch_eval_per_1k_rows":          0.80,   # batch eval (Foundry evals)
    "prompt_shields_per_1k_calls":     0.75,   # jailbreak / prompt-injection detection
    "red_team_per_run":                0.0,    # included in Foundry (preview)
}


def _resolve_model_key(model: str) -> str:
    m = (model or "").strip().lower()
    if m in FOUNDRY_PRICING_PER_1K:
        return m
    # fuzzy prefixes
    for k in FOUNDRY_PRICING_PER_1K:
        if m.startswith(k) or k.startswith(m):
            return k
    return "gpt-4o-mini"  # safe default


# ----------------------------------------------------------------------------
# Tools the agent can call
# ----------------------------------------------------------------------------
def calculate_foundry_token_cost(model: str, input_tokens: int, output_tokens: int) -> str:
    """Compute the USD cost for a single Microsoft Foundry model call given token counts."""
    key = _resolve_model_key(model)
    p = FOUNDRY_PRICING_PER_1K[key]
    in_cost = (input_tokens / 1000.0) * p["input"]
    out_cost = (output_tokens / 1000.0) * p["output"]
    total = in_cost + out_cost
    return (
        f"Model={key} | input={input_tokens} tok @ ${p['input']:.5f}/1K = ${in_cost:.5f} | "
        f"output={output_tokens} tok @ ${p['output']:.5f}/1K = ${out_cost:.5f} | "
        f"total=${total:.5f}"
    )


def estimate_agentic_app_cost(
    use_case: str,
    model: str,
    daily_active_users: int,
    sessions_per_user_per_day: int,
    turns_per_session: int,
    avg_input_tokens_per_turn: int,
    avg_output_tokens_per_turn: int,
    num_agents: int = 1,
    avg_run_duration_sec: float = 10.0,
    agent_vcpu: float = 1.0,
    agent_memory_gib: float = 4.0,
    uses_file_search: bool = False,
    uses_code_interpreter: bool = False,
    uses_web_search: bool = False,
    uses_custom_search: bool = False,
    uses_content_safety: bool = True,
    uses_prompt_shields: bool = False,
    uses_realtime_eval: bool = False,
    uses_batch_eval: bool = True,
    batch_eval_rows_per_month: int = 1000,
    observability_gb_per_month: float = 2.0,
    vector_store_gb: float = 1.0,
    thread_storage_gb: float = 0.5,
    uses_foundry_iq: bool = False,
    ai_search_tier: str = "basic",
    foundry_iq_queries_per_month: int = 0,
    foundry_iq_reasoning_level: str = "low",
    foundry_iq_retrieval_tokens_per_query: int = 2000,
) -> str:
    """Estimate monthly Microsoft Foundry cost for an agentic AI application."""
    key = _resolve_model_key(model)
    p = FOUNDRY_PRICING_PER_1K[key]
    fees = EXTRA_FOUNDRY_FEES

    calls_per_day = daily_active_users * sessions_per_user_per_day * turns_per_session
    calls_per_month = calls_per_day * 30
    runs_per_month = daily_active_users * sessions_per_user_per_day * 30
    in_tok_month = calls_per_month * avg_input_tokens_per_turn
    out_tok_month = calls_per_month * avg_output_tokens_per_turn

    # ── Model Token Cost ──
    in_cost = (in_tok_month / 1000.0) * p["input"]
    out_cost = (out_tok_month / 1000.0) * p["output"]
    model_cost = in_cost + out_cost

    # ── Agent Execution Cost ── (vCPU + memory pricing)
    total_agent_runs_month = runs_per_month * num_agents
    total_run_hours = total_agent_runs_month * (avg_run_duration_sec / 3600.0)
    vcpu_cost = total_run_hours * agent_vcpu * fees["agent_vcpu_per_hour"]
    mem_cost = total_run_hours * agent_memory_gib * fees["agent_memory_gib_per_hour"]
    thread_cost = thread_storage_gb * fees["thread_storage_per_gb_month"]
    exec_cost = vcpu_cost + mem_cost + thread_cost

    # ── Knowledge & Tools Cost ──
    # File search storage: $0.11/GB/day, first 1 GB free
    fs_storage_gb = max(vector_store_gb - 1.0, 0.0) if uses_file_search else 0.0
    fs_cost = fs_storage_gb * 30 * fees["file_search_storage_per_gb_day"] if uses_file_search else 0.0
    # Code interpreter: $0.033 per session
    ci_sessions_month = runs_per_month if uses_code_interpreter else 0
    ci_cost = ci_sessions_month * fees["code_interpreter_per_session"] if uses_code_interpreter else 0.0
    # Web / custom search
    ws_cost = (calls_per_month / 1000.0) * fees["web_search_per_1k_txn"] if uses_web_search else 0.0
    csearch_cost = (calls_per_month / 1000.0) * fees["custom_search_per_1k_txn"] if uses_custom_search else 0.0
    vs_cost = vector_store_gb * 30 * fees["vector_store_per_gb_day"] if uses_file_search else 0.0
    # ── Foundry IQ (AI Search + agentic reasoning) ──
    if uses_foundry_iq:
        tier_key = f"foundry_iq_search_{ai_search_tier.lower()}_monthly"
        iq_search_cost = fees.get(tier_key, fees["foundry_iq_search_basic_monthly"])
        iq_reasoning_cost = (foundry_iq_queries_per_month / 1000.0) * fees["foundry_iq_reasoning_per_1k"]
        # Retrieval token cost based on reasoning level
        total_retrieval_tokens = foundry_iq_queries_per_month * foundry_iq_retrieval_tokens_per_query
        if foundry_iq_reasoning_level.lower() == "medium":
            iq_retrieval_cost = (total_retrieval_tokens / 1_000_000.0) * fees["foundry_iq_retrieval_med_per_1m"]
        else:
            iq_retrieval_cost = (total_retrieval_tokens / 1_000_000.0) * fees["foundry_iq_retrieval_low_per_1m"]
    else:
        iq_search_cost = 0.0
        iq_reasoning_cost = 0.0
        iq_retrieval_cost = 0.0
        total_retrieval_tokens = 0
    foundry_iq_cost = iq_search_cost + iq_reasoning_cost + iq_retrieval_cost

    knowledge_cost = fs_cost + ci_cost + ws_cost + csearch_cost + vs_cost + foundry_iq_cost

    # ── Observability & Trust Cost ──
    obs_cost = observability_gb_per_month * fees["app_insights_per_gb"]
    cs_cost = (calls_per_month / 1000.0) * fees["content_safety_per_1k_calls"] if uses_content_safety else 0.0
    ps_cost = (calls_per_month / 1000.0) * fees["prompt_shields_per_1k_calls"] if uses_prompt_shields else 0.0
    rt_eval_cost = (total_agent_runs_month / 1000.0) * fees["realtime_eval_per_1k_runs"] if uses_realtime_eval else 0.0
    batch_eval_cost = (batch_eval_rows_per_month / 1000.0) * fees["batch_eval_per_1k_rows"] if uses_batch_eval else 0.0
    eval_cost = rt_eval_cost + batch_eval_cost
    trust_cost = obs_cost + cs_cost + ps_cost + eval_cost

    total = model_cost + exec_cost + knowledge_cost + trust_cost

    return (
        f"═══ {use_case} ═══\n"
        f"Model: {key}  |  Agents: {num_agents}  |  Avg run: {avg_run_duration_sec}s\n"
        f"Calls/month: {calls_per_month:,}  |  Agent runs/month: {total_agent_runs_month:,}\n\n"
        f"── MODEL TOKEN COST ──\n"
        f"  Input  {in_tok_month:,} tok → ${in_cost:,.2f}\n"
        f"  Output {out_tok_month:,} tok → ${out_cost:,.2f}\n"
        f"  Subtotal: ${model_cost:,.2f}\n\n"
        f"── AGENT EXECUTION COST ──\n"
        f"  Agent runs: {total_agent_runs_month:,} ({runs_per_month:,} sessions × {num_agents} agents)\n"
        f"  vCPU ({agent_vcpu} cores × {total_run_hours:,.1f} hrs @ $0.0994/hr): ${vcpu_cost:,.2f}\n"
        f"  Memory ({agent_memory_gib} GiB × {total_run_hours:,.1f} hrs @ $0.0118/GiB-hr): ${mem_cost:,.2f}\n"
        f"  Thread storage ({thread_storage_gb} GB): ${thread_cost:,.2f}\n"
        f"  Subtotal: ${exec_cost:,.2f}\n\n"
        f"── KNOWLEDGE & TOOLS COST ──\n"
        f"  File search storage ({vector_store_gb} GB, 1 GB free): ${fs_cost:,.2f}\n"
        f"  Code interpreter ({ci_sessions_month:,} sessions @ $0.033): ${ci_cost:,.2f}\n"
        f"  Web search: ${ws_cost:,.2f}\n"
        f"  Custom search: ${csearch_cost:,.2f}\n"
        f"  Vector store ({vector_store_gb} GB): ${vs_cost:,.2f}\n"
        f"  Foundry IQ – AI Search ({ai_search_tier}): ${iq_search_cost:,.2f}\n"
        f"  Foundry IQ – agentic reasoning ({foundry_iq_queries_per_month:,} queries): ${iq_reasoning_cost:,.2f}\n"
        f"  Subtotal: ${knowledge_cost:,.2f}\n\n"
        f"── OBSERVABILITY & TRUST COST ──\n"
        f"  App Insights ({observability_gb_per_month} GB): ${obs_cost:,.2f}\n"
        f"  Content Safety: ${cs_cost:,.2f}\n"
        f"  Prompt Shields: ${ps_cost:,.2f}\n"
        f"  Realtime eval ({total_agent_runs_month:,} runs): ${rt_eval_cost:,.2f}\n"
        f"  Batch eval ({batch_eval_rows_per_month:,} rows): ${batch_eval_cost:,.2f}\n"
        f"  Subtotal: ${trust_cost:,.2f}\n\n"
        f"══ ESTIMATED TOTAL / MONTH: ${total:,.2f} ══"
    )


# ----------------------------------------------------------------------------
# Helper tool — partial form update
# ----------------------------------------------------------------------------
def update_cost_parameters(**kwargs) -> str:
    """Accept any subset of cost parameters and confirm what was set."""
    accepted = {k: v for k, v in kwargs.items() if v is not None}
    if not accepted:
        return "No parameters provided."
    return f"Updated parameters: {', '.join(f'{k}={v}' for k, v in accepted.items())}"


def _build_cost_rows(**kw) -> list[list[str]]:
    """Re-compute the same cost breakdown and return as rows for CSV export."""
    fees = EXTRA_FOUNDRY_FEES
    key = _resolve_model_key(kw["model"])
    p = FOUNDRY_PRICING_PER_1K[key]
    dau = kw["daily_active_users"]
    spd = kw["sessions_per_user_per_day"]
    tps = kw["turns_per_session"]
    calls_mo = dau * spd * tps * 30
    runs_mo = dau * spd * 30
    n_agents = kw.get("num_agents", 1)
    total_runs = runs_mo * n_agents
    in_tok = calls_mo * kw["avg_input_tokens_per_turn"]
    out_tok = calls_mo * kw["avg_output_tokens_per_turn"]
    run_dur = kw.get("avg_run_duration_sec", 10.0)
    agent_vcpu = kw.get("agent_vcpu", 1.0)
    agent_mem_gib = kw.get("agent_memory_gib", 4.0)
    total_run_hours = total_runs * (run_dur / 3600.0)
    thread_gb = kw.get("thread_storage_gb", 0.5)
    vs_gb = kw.get("vector_store_gb", 1.0)

    rows: list[list[str]] = []

    def _r(cat: str, item: str, detail: str, cost: float):
        rows.append([cat, item, detail, f"{cost:.4f}"])

    # Model token cost
    in_c = (in_tok / 1000.0) * p["input"]
    out_c = (out_tok / 1000.0) * p["output"]
    _r("Model Tokens", "Input tokens", f"{in_tok:,} tok", in_c)
    _r("Model Tokens", "Output tokens", f"{out_tok:,} tok", out_c)
    _r("Model Tokens", "Subtotal", "", in_c + out_c)

    # Agent execution (vCPU + memory)
    vcpu_c = total_run_hours * agent_vcpu * fees["agent_vcpu_per_hour"]
    mem_c = total_run_hours * agent_mem_gib * fees["agent_memory_gib_per_hour"]
    thr_c = thread_gb * fees["thread_storage_per_gb_month"]
    _r("Agent Execution", "vCPU", f"{agent_vcpu} cores × {total_run_hours:,.1f} hrs", vcpu_c)
    _r("Agent Execution", "Memory", f"{agent_mem_gib} GiB × {total_run_hours:,.1f} hrs", mem_c)
    _r("Agent Execution", "Thread storage", f"{thread_gb} GB", thr_c)
    exec_sub = vcpu_c + mem_c + thr_c
    _r("Agent Execution", "Subtotal", "", exec_sub)

    # Knowledge & tools
    fs_gb_billable = max(vs_gb - 1.0, 0.0) if kw.get("uses_file_search") else 0.0
    fs_c = fs_gb_billable * 30 * fees["file_search_storage_per_gb_day"] if kw.get("uses_file_search") else 0.0
    ci_sessions = runs_mo if kw.get("uses_code_interpreter") else 0
    ci_c = ci_sessions * fees["code_interpreter_per_session"] if kw.get("uses_code_interpreter") else 0.0
    ws_c = (calls_mo / 1000.0) * fees["web_search_per_1k_txn"] if kw.get("uses_web_search") else 0.0
    csearch_c = (calls_mo / 1000.0) * fees["custom_search_per_1k_txn"] if kw.get("uses_custom_search") else 0.0
    vs_c = vs_gb * 30 * fees["vector_store_per_gb_day"] if kw.get("uses_file_search") else 0.0
    _r("Knowledge & Tools", "File search storage", f"{vs_gb} GB (1 GB free)", fs_c)
    _r("Knowledge & Tools", "Code interpreter", f"{ci_sessions:,} sessions", ci_c)
    _r("Knowledge & Tools", "Web search (Bing)", "", ws_c)
    _r("Knowledge & Tools", "Custom search", "", csearch_c)
    _r("Knowledge & Tools", "Vector store", f"{vs_gb} GB", vs_c)

    # Foundry IQ
    iq_s = iq_r = iq_ret = 0.0
    fiq_queries = kw.get("foundry_iq_queries_per_month", 0)
    fiq_ret_tok = kw.get("foundry_iq_retrieval_tokens_per_query", 2000)
    fiq_lvl = kw.get("foundry_iq_reasoning_level", "low")
    if kw.get("uses_foundry_iq"):
        tier = kw.get("ai_search_tier", "basic")
        iq_s = fees.get(f"foundry_iq_search_{tier}_monthly", fees["foundry_iq_search_basic_monthly"])
        iq_r = (fiq_queries / 1000.0) * fees["foundry_iq_reasoning_per_1k"]
        tot_ret = fiq_queries * fiq_ret_tok
        rate_key = "foundry_iq_retrieval_med_per_1m" if fiq_lvl == "medium" else "foundry_iq_retrieval_low_per_1m"
        iq_ret = (tot_ret / 1_000_000.0) * fees[rate_key]
    else:
        tier = kw.get("ai_search_tier", "basic")
        tot_ret = 0
    _r("Knowledge & Tools", f"Foundry IQ – AI Search ({tier})", "", iq_s)
    _r("Knowledge & Tools", f"Foundry IQ – agentic reasoning", f"{fiq_queries:,} queries", iq_r)
    _r("Knowledge & Tools", f"Foundry IQ – retrieval tokens ({fiq_lvl})", f"{tot_ret:,} tok", iq_ret)
    know_total = fs_c + ci_c + ws_c + csearch_c + vs_c + iq_s + iq_r + iq_ret
    _r("Knowledge & Tools", "Subtotal", "", know_total)

    # Observability & trust
    obs_gb = kw.get("observability_gb_per_month", 2.0)
    obs_c = obs_gb * fees["app_insights_per_gb"]
    cs_c = (calls_mo / 1000.0) * fees["content_safety_per_1k_calls"] if kw.get("uses_content_safety") else 0.0
    ps_c = (calls_mo / 1000.0) * fees["prompt_shields_per_1k_calls"] if kw.get("uses_prompt_shields") else 0.0
    rt_e = (total_runs / 1000.0) * fees["realtime_eval_per_1k_runs"] if kw.get("uses_realtime_eval") else 0.0
    batch_rows = kw.get("batch_eval_rows_per_month", 0)
    bt_e = (batch_rows / 1000.0) * fees["batch_eval_per_1k_rows"] if kw.get("uses_batch_eval") else 0.0
    _r("Observability & Trust", "App Insights", f"{obs_gb} GB", obs_c)
    _r("Observability & Trust", "Content Safety", "", cs_c)
    _r("Observability & Trust", "Prompt Shields", "", ps_c)
    _r("Observability & Trust", "Realtime eval", f"{total_runs:,} runs", rt_e)
    _r("Observability & Trust", "Batch eval", f"{batch_rows:,} rows", bt_e)
    _r("Observability & Trust", "Subtotal", "", obs_c + cs_c + ps_c + rt_e + bt_e)

    # Grand total
    grand = (in_c + out_c) + exec_sub + know_total + (obs_c + cs_c + ps_c + rt_e + bt_e)
    _r("TOTAL", "Estimated monthly cost", kw.get("use_case", ""), grand)

    return rows


# ----------------------------------------------------------------------------
# Agent setup — OpenAI function-calling with Azure OpenAI
# ----------------------------------------------------------------------------
SYSTEM_PROMPT = """You are FoundryPricingAdvisor, an expert on Microsoft Foundry agentic
AI applications. You help users reason about:
  • Microsoft Foundry agent usage patterns (hosted agents, threads, runs)
  • Model selection and token usage (input vs output, context windows)
  • Knowledge & tools (file search, code interpreter, function tools, MCP)
  • Observability & trust (App Insights, tracing, evaluations, content safety, RAI)
  • Cost & pricing estimation for agentic applications

IMPORTANT RULES:
1. When the user EXPLICITLY mentions a cost-related value in their LATEST message
   (model, users, turns, agents, features, etc.), call update_cost_parameters with
   ONLY those fields. NEVER include fields the user did not explicitly mention in
   their latest message — do not guess, do not re-send previous values, do not fill
   in defaults. The calculator already holds the current values for every other
   field; leaving a field out keeps it unchanged.
2. A `[CURRENT_FORM_STATE]` block is injected before each user message showing the
   values currently in the calculator. Use these as the source of truth for any
   field the user did NOT mention. Pass them ONLY as arguments to
   estimate_agentic_app_cost / calculate_foundry_token_cost when producing an
   estimate — NEVER echo them back through update_cost_parameters.
3. After updating parameters, if you still need more info, ask ONE short
   clarifying question.
4. Once you have enough info, call estimate_agentic_app_cost or
   calculate_foundry_token_cost to produce the full estimate, using the current
   form state for any field the user has not specified.
5. Keep answers concise (<=180 words) and use bullet points where helpful.
"""

TOOLS_SCHEMA = [
    {
        "type": "function",
        "name": "calculate_foundry_token_cost",
        "description": "Compute the USD cost for a single Microsoft Foundry model call given token counts.",
        "parameters": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Foundry/Azure OpenAI model name, e.g. gpt-4o-mini, gpt-5-mini, gpt-4.1."},
                "input_tokens": {"type": "integer", "description": "Number of input (prompt) tokens."},
                "output_tokens": {"type": "integer", "description": "Number of output (completion) tokens."},
            },
            "required": ["model", "input_tokens", "output_tokens"],
        },
    },
    {
        "type": "function",
        "name": "estimate_agentic_app_cost",
        "description": "Estimate monthly Microsoft Foundry cost for an agentic AI application including model tokens, agent execution, knowledge & tools, and observability & trust.",
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {"type": "string", "description": "Short description of the agentic AI use case."},
                "model": {"type": "string", "description": "Primary Foundry model used for reasoning."},
                "daily_active_users": {"type": "integer", "description": "Expected daily active users."},
                "sessions_per_user_per_day": {"type": "integer", "description": "Average sessions each user starts per day."},
                "turns_per_session": {"type": "integer", "description": "Average chat turns per session."},
                "avg_input_tokens_per_turn": {"type": "integer", "description": "Average prompt tokens per turn (incl. system + RAG context)."},
                "avg_output_tokens_per_turn": {"type": "integer", "description": "Average completion tokens per turn."},
                "num_agents": {"type": "integer", "description": "Number of agents invoked per session (e.g. 1 for single agent, 3 for a multi-agent workflow)."},
                "avg_run_duration_sec": {"type": "number", "description": "Average wall-clock duration in seconds for each agent run."},
                "agent_vcpu": {"type": "number", "description": "vCPU cores allocated per hosted agent (default 1)."},
                "agent_memory_gib": {"type": "number", "description": "Memory in GiB allocated per hosted agent (default 4)."},
                "uses_file_search": {"type": "boolean", "description": "True if the app uses Foundry file search / vector store."},
                "uses_code_interpreter": {"type": "boolean", "description": "True if the app enables Code Interpreter ($0.033/session)."},
                "uses_web_search": {"type": "boolean", "description": "True if using Bing web search tool ($14/1K transactions)."},
                "uses_custom_search": {"type": "boolean", "description": "True if using custom search tool ($14/1K transactions)."},
                "uses_content_safety": {"type": "boolean", "description": "True if using Azure AI Content Safety."},
                "uses_prompt_shields": {"type": "boolean", "description": "True if using Prompt Shields (jailbreak detection)."},
                "uses_realtime_eval": {"type": "boolean", "description": "True if every agent execution also runs an evaluation (realtime eval). Cost scales with agent runs."},
                "uses_batch_eval": {"type": "boolean", "description": "True if using Foundry batch evaluations on a fixed dataset."},
                "batch_eval_rows_per_month": {"type": "integer", "description": "Number of batch evaluation rows per month."},
                "observability_gb_per_month": {"type": "number", "description": "Estimated App Insights ingestion in GB per month."},
                "vector_store_gb": {"type": "number", "description": "Vector store size in GB."},
                "thread_storage_gb": {"type": "number", "description": "Thread/message storage in GB."},
                "uses_foundry_iq": {"type": "boolean", "description": "True if using Foundry IQ (Azure AI Search with agentic reasoning)."},
                "ai_search_tier": {"type": "string", "enum": ["basic", "s1", "s2"], "description": "Azure AI Search tier for Foundry IQ: basic, s1, or s2."},
                "foundry_iq_queries_per_month": {"type": "integer", "description": "Number of Foundry IQ agentic reasoning queries per month."},
                "foundry_iq_reasoning_level": {"type": "string", "enum": ["low", "medium"], "description": "Foundry IQ reasoning level: low (minimal, $0.022/1M tok) or medium ($0.10/1M tok)."},
                "foundry_iq_retrieval_tokens_per_query": {"type": "integer", "description": "Average retrieval tokens per Foundry IQ query."},
            },
            "required": ["use_case", "model", "daily_active_users", "sessions_per_user_per_day",
                         "turns_per_session", "avg_input_tokens_per_turn", "avg_output_tokens_per_turn"],
        },
    },
    {
        "type": "function",
        "name": "update_cost_parameters",
        "description": "Update the cost calculator form with partial information extracted from the conversation. Call this IMMEDIATELY whenever the user mentions any cost-relevant detail (model, users, agents, features, etc.) to keep the UI in sync.",
        "parameters": {
            "type": "object",
            "properties": {
                "use_case": {"type": "string", "description": "Short description of the use case."},
                "model": {"type": "string", "description": "Model name, e.g. gpt-4o, gpt-5-mini."},
                "daily_active_users": {"type": "integer", "description": "Expected daily active users."},
                "sessions_per_user_per_day": {"type": "integer", "description": "Sessions per user per day."},
                "turns_per_session": {"type": "integer", "description": "Turns per session."},
                "avg_input_tokens_per_turn": {"type": "integer", "description": "Average input tokens per turn."},
                "avg_output_tokens_per_turn": {"type": "integer", "description": "Average output tokens per turn."},
                "num_agents": {"type": "integer", "description": "Number of agents per session."},
                "avg_run_duration_sec": {"type": "number", "description": "Average agent run duration in seconds."},
                "agent_vcpu": {"type": "number", "description": "vCPU cores per agent."},
                "agent_memory_gib": {"type": "number", "description": "Memory GiB per agent."},
                "uses_file_search": {"type": "boolean", "description": "Whether file search is used."},
                "uses_code_interpreter": {"type": "boolean", "description": "Whether code interpreter is used."},
                "uses_web_search": {"type": "boolean", "description": "Whether web search is used."},
                "uses_custom_search": {"type": "boolean", "description": "Whether custom search is used."},
                "uses_content_safety": {"type": "boolean", "description": "Whether content safety is used."},
                "uses_prompt_shields": {"type": "boolean", "description": "Whether prompt shields are used."},
                "uses_realtime_eval": {"type": "boolean", "description": "Whether realtime eval is used."},
                "uses_batch_eval": {"type": "boolean", "description": "Whether batch eval is used."},
                "batch_eval_rows_per_month": {"type": "integer", "description": "Batch eval rows per month."},
                "observability_gb_per_month": {"type": "number", "description": "App Insights GB per month."},
                "vector_store_gb": {"type": "number", "description": "Vector store size in GB."},
                "uses_foundry_iq": {"type": "boolean", "description": "Whether Foundry IQ is used."},
                "ai_search_tier": {"type": "string", "description": "AI Search tier: basic, s1, or s2."},
                "foundry_iq_queries_per_month": {"type": "integer", "description": "Foundry IQ queries per month."},
                "foundry_iq_reasoning_level": {"type": "string", "description": "Foundry IQ reasoning level: low or medium."},
                "foundry_iq_retrieval_tokens_per_query": {"type": "integer", "description": "Retrieval tokens per Foundry IQ query."},
            },
            "required": [],
        },
    },
]

TOOL_DISPATCH = {
    "calculate_foundry_token_cost": calculate_foundry_token_cost,
    "estimate_agentic_app_cost": estimate_agentic_app_cost,
    "update_cost_parameters": update_cost_parameters,
}


@st.cache_resource(show_spinner=False)
def get_client() -> AzureOpenAI:
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        "https://cognitiveservices.azure.com/.default",
    )
    return AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_ad_token_provider=token_provider,
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview"),
    )


def ask_agent_sync(messages: list[dict]) -> tuple[str, dict[str, int], dict[str, Any]]:
    """Send conversation to Azure OpenAI Responses API with tool calling."""
    client = get_client()
    deployment = (
        os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or "gpt-5.4-mini"
    )

    # Build input for Responses API (use "developer" role for system prompt)
    api_input: list = [{"role": "developer", "content": SYSTEM_PROMPT}] + messages

    total_usage: dict[str, int] = {"input": 0, "output": 0, "total": 0}
    last_tool_args: dict[str, Any] = {}
    last_tool_name: str = ""

    # Allow up to 3 round-trips for tool calls
    for _ in range(3):
        response = client.responses.create(
            model=deployment,
            input=api_input,
            tools=TOOLS_SCHEMA,
            temperature=0.3,
        )
        # Accumulate usage
        if response.usage:
            total_usage["input"] += response.usage.input_tokens or 0
            total_usage["output"] += response.usage.output_tokens or 0
            total_usage["total"] += (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        # Check for function_call items in the output
        function_calls = [item for item in response.output if item.type == "function_call"]

        if not function_calls:
            # Final text answer
            return response.output_text or "", total_usage, last_tool_args, last_tool_name

        # Append all output items (assistant message + function_call) to input
        for item in response.output:
            api_input.append(item.model_dump())

        # Execute each function call and feed results back
        for fc in function_calls:
            fn_name = fc.name
            fn_args = json.loads(fc.arguments)
            # Only update_cost_parameters drives form sync (sends only user-mentioned
            # fields). estimate_agentic_app_cost requires ALL params and would
            # overwrite user-tuned values with agent guesses, so we ignore it here.
            if fn_name == "update_cost_parameters":
                last_tool_args.update(fn_args)
                last_tool_name = fn_name
            fn = TOOL_DISPATCH.get(fn_name)
            result = fn(**fn_args) if fn else f"Unknown tool: {fn_name}"
            api_input.append({
                "type": "function_call_output",
                "call_id": fc.call_id,
                "output": str(result),
            })

    # Fallback if loop exhausted
    return response.output_text or "I couldn't complete the request.", total_usage, last_tool_args, last_tool_name


# ----------------------------------------------------------------------------
# Session state
# ----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []  # list[{"role","content","usage"?}]
if "usage_total" not in st.session_state:
    st.session_state.usage_total = {"input": 0, "output": 0, "total": 0}
if "turns" not in st.session_state:
    st.session_state.turns = 0
# Form defaults populated by chat agent tool calls
if "form" not in st.session_state:
    st.session_state.form = {
        "use_case": "Customer support copilot",
        "model": None,  # None = use current deployment
        "daily_active_users": 500,
        "sessions_per_user_per_day": 2,
        "turns_per_session": 6,
        "avg_input_tokens_per_turn": 1200,
        "avg_output_tokens_per_turn": 300,
        "num_agents": 1,
        "avg_run_duration_sec": 10.0,
        "agent_vcpu": 1.0,
        "agent_memory_gib": 4.0,
        "uses_file_search": True,
        "uses_code_interpreter": False,
        "uses_web_search": False,
        "uses_custom_search": False,
        "vector_store_gb": 1.0,
        "uses_content_safety": True,
        "uses_prompt_shields": False,
        "uses_realtime_eval": False,
        "uses_batch_eval": True,
        "batch_eval_rows_per_month": 1000,
        "observability_gb_per_month": 2.0,
        "uses_foundry_iq": False,
        "ai_search_tier": "basic",
        "foundry_iq_queries_per_month": 10000,
        "foundry_iq_reasoning_level": "low",
        "foundry_iq_retrieval_tokens_per_query": 2000,
    }

# Apply any pending widget updates from the previous chat turn BEFORE widgets
# render this run. (Streamlit forbids writing to session_state[widget_key] after
# the widget has been instantiated in the same run, so we stage updates in
# `pending_widget_updates` and flush them here at the top.)
_pending = st.session_state.pop("pending_widget_updates", None)
if _pending:
    for _wkey, _wval in _pending.items():
        st.session_state[_wkey] = _wval

# Seed widget-bound session_state keys from the form defaults BEFORE widgets
# render. Once seeded, widgets read their value from session_state via key=,
# so we omit the `value=` argument on the widgets to avoid Streamlit's
# "created with default value but also had its value set via Session State"
# warning. Min-value clamping mirrors the per-widget min_value.
_WIDGET_MINS: dict[str, float] = {
    "daily_active_users": 1, "sessions_per_user_per_day": 1,
    "turns_per_session": 1, "avg_input_tokens_per_turn": 1,
    "avg_output_tokens_per_turn": 1, "num_agents": 1,
    "avg_run_duration_sec": 1.0, "agent_vcpu": 0.25,
    "agent_memory_gib": 0.5, "foundry_iq_retrieval_tokens_per_query": 100,
}
for _fk, _fv in st.session_state.form.items():
    _wk = f"cf_{_fk}"
    if _wk in st.session_state:
        continue
    if _fv is None:
        # Skip None defaults (e.g. "model"); they're seeded in-form where the
        # active deployment is known.
        continue
    if _fk in _WIDGET_MINS and isinstance(_fv, (int, float)):
        _fv = max(_WIDGET_MINS[_fk], _fv)
    st.session_state[_wk] = _fv


# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
top_l, top_r = st.columns([0.75, 0.25])
with top_l:
    st.markdown('<div class="app-title">💸 Microsoft Foundry Pricing & Agent Advisor</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="app-sub">Ask about Foundry agent usage, token usage, knowledge & tools, observability, and application cost.</div>',
        unsafe_allow_html=True,
    )
with top_r:
    model_label = (
        os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or "n/a"
    )
    st.markdown(
        f"<div class='small-note' style='text-align:right;'>Model: <b>{model_label}</b> &nbsp;|&nbsp; "
        f"Turns: <b>{st.session_state.turns}</b></div>",
        unsafe_allow_html=True,
    )

# ----------------------------------------------------------------------------
# Two-column layout: cost estimator + token (left) | conversation (right)
# ----------------------------------------------------------------------------
left, right = st.columns([0.50, 0.50], gap="medium")

with right:
    st.markdown("**🗨️ Conversation**")
    chat_box = st.container(height=500, border=True)
    with chat_box:
        if not st.session_state.messages:
            st.caption(
                "Try: *“What does it cost to run a 1,000-user copilot using gpt-4o-mini "
                "with file search?”* or *“How do I observe a Foundry agent in production?”*"
            )
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])    # Chat input pinned at the bottom of the right column
    prompt = st.chat_input("Ask about Foundry agents, tokens, tools, observability, or cost\u2026")
with left:
    cost_box = st.container(height=600, border=False)
    with cost_box:
        tot = st.session_state.usage_total
        with st.expander("📊 Token usage (session)", expanded=True):
            c1, c2, c3 = st.columns(3)
            c1.metric("Input", f"{tot['input']:,}")
            c2.metric("Output", f"{tot['output']:,}")
            c3.metric("Total", f"{tot['total']:,}")
            # Per-turn breakdown
            last = [m for m in st.session_state.messages if m.get("usage")][-5:]
            if last:
                st.caption("Last turns:")
                for i, m in enumerate(last, 1):
                    u = m["usage"]
                    st.markdown(
                        f"<span class='small-note'>#{i} • in {u['input']:,} / out {u['output']:,} / "
                        f"total {u['total']:,}</span>",
                        unsafe_allow_html=True,
                    )

        with st.expander("💰 Foundry application cost", expanded=True):
            # Live cost for current session usage at selected model
            key = _resolve_model_key(model_label)
            p = FOUNDRY_PRICING_PER_1K[key]
            sess_in_cost = (tot["input"] / 1000.0) * p["input"]
            sess_out_cost = (tot["output"] / 1000.0) * p["output"]
            sess_total = sess_in_cost + sess_out_cost
            st.markdown(
                f"**Session cost** ({key}): "
                f"`${sess_total:.5f}`  \n"
                f"<span class='small-note'>in ${sess_in_cost:.5f} + out ${sess_out_cost:.5f}</span>",
                unsafe_allow_html=True,
            )
            st.divider()
            st.markdown("**Full app estimate**")
            fd = st.session_state.form  # shorthand
            model_keys = list(FOUNDRY_PRICING_PER_1K.keys())
            form_model_key = _resolve_model_key(fd["model"]) if fd["model"] else key
            with st.form("cost_form", border=False):
                use_case = st.text_input("Use case", key="cf_use_case")
                cc1, cc2 = st.columns(2)
                with cc1:
                    # Model selectbox: keep `index=` only on first render (no key in state yet)
                    if "cf_model" not in st.session_state:
                        st.session_state["cf_model"] = form_model_key if form_model_key in model_keys else model_keys[1]
                    model_in = st.selectbox("Model", options=model_keys, key="cf_model")
                    dau = st.number_input("Daily active users", min_value=1, step=50, key="cf_daily_active_users")
                    sess = st.number_input("Sessions / user / day", min_value=1, step=1, key="cf_sessions_per_user_per_day")
                    turns = st.number_input("Turns / session", min_value=1, step=1, key="cf_turns_per_session")
                    in_tok = st.number_input("Avg input tok / turn", min_value=1, step=100, key="cf_avg_input_tokens_per_turn")
                    out_tok = st.number_input("Avg output tok / turn", min_value=1, step=50, key="cf_avg_output_tokens_per_turn")
                    st.caption("Agent Execution")
                    n_agents = st.number_input("Number of agents", min_value=1, step=1, key="cf_num_agents")
                    run_dur = st.number_input("Avg run duration (sec)", min_value=1.0, step=5.0, key="cf_avg_run_duration_sec")
                    agent_vcpu = st.number_input("vCPU per agent", min_value=0.25, step=0.5, key="cf_agent_vcpu")
                    agent_mem = st.number_input("Memory (GiB) per agent", min_value=0.5, step=1.0, key="cf_agent_memory_gib")
                with cc2:
                    st.caption("Knowledge & Tools")
                    use_fs = st.checkbox("File search / vector store", key="cf_uses_file_search")
                    use_ci = st.checkbox("Code interpreter", key="cf_uses_code_interpreter")
                    use_ws = st.checkbox("Web search (Bing)", key="cf_uses_web_search")
                    use_csearch = st.checkbox("Custom search", key="cf_uses_custom_search")
                    vs_gb = st.number_input("Vector store (GB)", min_value=0.0, step=0.5, key="cf_vector_store_gb")
                    st.caption("Foundry IQ")
                    use_fiq = st.checkbox("Foundry IQ (AI Search + reasoning)", key="cf_uses_foundry_iq")
                    ai_tier = st.selectbox("AI Search tier", options=["basic", "s1", "s2"], key="cf_ai_search_tier")
                    fiq_queries = st.number_input("IQ queries / month", min_value=0, step=5000, key="cf_foundry_iq_queries_per_month")
                    fiq_reason_lvl = st.selectbox("IQ reasoning level", options=["low", "medium"], key="cf_foundry_iq_reasoning_level")
                    fiq_ret_tok = st.number_input("Retrieval tok / query", min_value=100, step=500, key="cf_foundry_iq_retrieval_tokens_per_query")
                    st.caption("Observability & Trust")
                    use_cs = st.checkbox("Content Safety", key="cf_uses_content_safety")
                    use_ps = st.checkbox("Prompt Shields", key="cf_uses_prompt_shields")
                    use_rt_eval = st.checkbox("Realtime eval (per run)", key="cf_uses_realtime_eval")
                    use_batch_eval = st.checkbox("Batch eval", key="cf_uses_batch_eval")
                    batch_eval_rows = st.number_input("Batch eval rows / month", min_value=0, step=500, key="cf_batch_eval_rows_per_month")
                    obs_gb = st.number_input("App Insights (GB/mo)", min_value=0.0, step=1.0, key="cf_observability_gb_per_month")
                submitted = st.form_submit_button("Estimate", use_container_width=True)
            if submitted:
                # Persist current widget values back to session state
                fd.update({
                    "use_case": use_case, "model": model_in,
                    "daily_active_users": int(dau),
                    "sessions_per_user_per_day": int(sess),
                    "turns_per_session": int(turns),
                    "avg_input_tokens_per_turn": int(in_tok),
                    "avg_output_tokens_per_turn": int(out_tok),
                    "num_agents": int(n_agents),
                    "avg_run_duration_sec": float(run_dur),
                    "agent_vcpu": float(agent_vcpu),
                    "agent_memory_gib": float(agent_mem),
                    "uses_file_search": bool(use_fs),
                    "uses_code_interpreter": bool(use_ci),
                    "uses_web_search": bool(use_ws),
                    "uses_custom_search": bool(use_csearch),
                    "uses_foundry_iq": bool(use_fiq),
                    "ai_search_tier": str(ai_tier),
                    "foundry_iq_queries_per_month": int(fiq_queries),
                    "foundry_iq_reasoning_level": str(fiq_reason_lvl),
                    "foundry_iq_retrieval_tokens_per_query": int(fiq_ret_tok),
                    "uses_content_safety": bool(use_cs),
                    "uses_prompt_shields": bool(use_ps),
                    "uses_realtime_eval": bool(use_rt_eval),
                    "uses_batch_eval": bool(use_batch_eval),
                    "batch_eval_rows_per_month": int(batch_eval_rows),
                    "observability_gb_per_month": float(obs_gb),
                    "vector_store_gb": float(vs_gb),
                })
                # Build kwargs once, reuse for estimate + CSV export
                cost_kw = {k: v for k, v in fd.items() if k != "model" and v is not None}
                cost_kw["model"] = fd["model"] or model_label
                est = estimate_agentic_app_cost(**cost_kw)
                st.code(est, language="text")
                # ── Export to CSV / Excel ──
                rows = _build_cost_rows(**cost_kw)
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["Category", "Line Item", "Detail", "Monthly Cost (USD)"])
                for r in rows:
                    writer.writerow(r)
                csv_bytes = buf.getvalue().encode("utf-8")
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button("📥 Export CSV", data=csv_bytes,
                                       file_name="foundry_cost_estimate.csv",
                                       mime="text/csv", use_container_width=True)
                with dl2:
                    try:
                        import openpyxl  # noqa: F401
                        import pandas as pd
                        df = pd.DataFrame(rows, columns=["Category", "Line Item", "Detail", "Monthly Cost (USD)"])
                        xbuf = io.BytesIO()
                        df.to_excel(xbuf, index=False, sheet_name="Estimate")
                        st.download_button("📥 Export Excel", data=xbuf.getvalue(),
                                           file_name="foundry_cost_estimate.xlsx",
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           use_container_width=True)
                    except ImportError:
                        st.download_button("📥 Export CSV (Excel needs openpyxl)", data=csv_bytes,
                                           file_name="foundry_cost_estimate.csv",
                                           mime="text/csv", use_container_width=True, disabled=True)

# ----------------------------------------------------------------------------
# Handle chat input (prompt captured inside right column above)
# ----------------------------------------------------------------------------

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    # Build API-compatible messages (strip 'usage' key for the call)
    api_msgs = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    # Inject current form state as a developer note right before the latest user
    # message so the agent knows existing values and doesn't echo them back through
    # update_cost_parameters (which would overwrite user-tuned inputs).
    _form_snapshot = json.dumps(st.session_state.form, indent=2, default=str)
    api_msgs.insert(
        len(api_msgs) - 1,
        {
            "role": "developer",
            "content": (
                "[CURRENT_FORM_STATE] These values are already set in the calculator. "
                "Do NOT pass any of these to update_cost_parameters unless the user "
                "explicitly asks to change them in the next message. Use them only as "
                "defaults when invoking estimate_agentic_app_cost.\n" + _form_snapshot
            ),
        },
    )
    with st.spinner("Thinking…", show_time=True):
        try:
            answer, usage, tool_args, tool_name = ask_agent_sync(api_msgs)
        except Exception as e:
            answer = f"\u26a0\ufe0f Agent error: {e}"
            usage = {"input": 0, "output": 0, "total": 0}
            tool_args = {}
            tool_name = ""

    st.session_state.messages.append(
        {"role": "assistant", "content": answer, "usage": usage}
    )
    st.session_state.usage_total["input"] += usage["input"]
    st.session_state.usage_total["output"] += usage["output"]
    st.session_state.usage_total["total"] += usage["total"]
    st.session_state.turns += 1

    # Update form: only fields the user explicitly mentioned via update_cost_parameters.
    # estimate_agentic_app_cost is intentionally ignored for form sync because it
    # requires ALL params and would overwrite user-tuned values with agent guesses.
    if tool_args and tool_name == "update_cost_parameters":
        fd = st.session_state.form
        # Minimum constraints matching the form widgets
        _MINS = {
            "daily_active_users": 1, "sessions_per_user_per_day": 1,
            "turns_per_session": 1, "avg_input_tokens_per_turn": 1,
            "avg_output_tokens_per_turn": 1, "num_agents": 1,
            "avg_run_duration_sec": 1.0, "agent_vcpu": 0.25,
            "agent_memory_gib": 0.5, "foundry_iq_retrieval_tokens_per_query": 100,
        }
        # Synonyms / keywords the user might type for each field. We accept a
        # field from the agent ONLY if at least one of its keywords appears in
        # the user's latest message. This is a strict server-side guard because
        # the LLM sometimes ignores prompt instructions and re-sends fields the
        # user didn't actually mention.
        _KEYWORDS: dict[str, tuple[str, ...]] = {
            "use_case": ("use case", "scenario", "application", "app for"),
            "model": ("model", "gpt", "o1", "o3", "deployment"),
            "daily_active_users": ("dau", "daily active", "users", "user count", "active user"),
            "sessions_per_user_per_day": ("session", "sessions"),
            "turns_per_session": ("turn", "turns", "exchange", "messages per"),
            "avg_input_tokens_per_turn": ("input token", "prompt token", "input tok"),
            "avg_output_tokens_per_turn": ("output token", "completion token", "output tok"),
            "num_agents": ("agent count", "number of agents", "num agents", "agents per", "multi-agent", "multi agent", "how many agents"),
            "avg_run_duration_sec": ("run duration", "duration", "seconds per run", "run time", "latency"),
            "agent_vcpu": ("vcpu", "cpu core", "cores"),
            "agent_memory_gib": ("memory", "gib", "ram"),
            "uses_file_search": ("file search", "vector store", "rag", "retrieval"),
            "uses_code_interpreter": ("code interpreter", "code exec"),
            "uses_web_search": ("web search", "bing"),
            "uses_custom_search": ("custom search",),
            "uses_content_safety": ("content safety",),
            "uses_prompt_shields": ("prompt shield", "jailbreak"),
            "uses_realtime_eval": ("realtime eval", "real-time eval", "online eval"),
            "uses_batch_eval": ("batch eval",),
            "batch_eval_rows_per_month": ("eval row", "batch row"),
            "observability_gb_per_month": ("observability", "app insights", "telemetry", "logs"),
            "vector_store_gb": ("vector store", "vector gb", "index size"),
            "uses_foundry_iq": ("foundry iq", "foundryiq", "iq"),
            "ai_search_tier": ("search tier", "ai search tier", "basic tier", "s1", "s2"),
            "foundry_iq_queries_per_month": ("iq quer", "foundry iq quer", "search quer"),
            "foundry_iq_reasoning_level": ("reasoning level", "iq reasoning"),
            "foundry_iq_retrieval_tokens_per_query": ("retrieval token",),
        }
        prompt_lower = prompt.lower()

        def _user_mentioned(field: str) -> bool:
            kws = _KEYWORDS.get(field, ())
            return any(kw in prompt_lower for kw in kws)

        # Only apply changes for fields the user actually mentioned. As an extra
        # guard against the agent re-sending unchanged values, skip any field
        # whose proposed value already equals the current form value.
        pending: dict[str, Any] = {}
        for k, v in tool_args.items():
            if k not in fd:
                continue
            if not _user_mentioned(k):
                continue  # agent guessed a field the user didn't mention — ignore
            new_v = max(_MINS[k], v) if k in _MINS else v
            if fd[k] == new_v:
                continue
            fd[k] = new_v
            # Stage the widget update; it will be flushed into session_state at
            # the top of the next run, BEFORE widgets render (Streamlit forbids
            # writing to a widget's session_state key after instantiation).
            pending[f"cf_{k}"] = new_v
        if pending:
            st.session_state["pending_widget_updates"] = pending

    st.rerun()
