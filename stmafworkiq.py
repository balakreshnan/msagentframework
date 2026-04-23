# Copyright (c) Microsoft. All rights reserved.
"""
stmafworkiq.py
==============
Streamlit UI demonstrating a Microsoft Agent Framework **orchestrator agent**
(`ChatAgent` backed by ``AzureOpenAIChatClient``) that calls the Microsoft
Foundry hosted **``workiqagent``** as a tool.

Architecture
------------
    User ──► [MAF Orchestrator ChatAgent (Azure OpenAI)]
                 │   tools = [ask_workiq_agent]
                 ▼
            Foundry hosted ``workiqagent``  (Responses API · agent_reference)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from typing import Annotated

import streamlit as st
from dotenv import load_dotenv
from pydantic import Field

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

# Microsoft Agent Framework
from agent_framework import Agent
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework.orchestrations import (
    MagenticBuilder,
    MagenticOrchestratorEvent,
    StandardMagenticManager,
)
from agent_framework.observability import get_tracer
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AZURE_AI_PROJECT = os.getenv("AZURE_AI_PROJECT")
AGENT_NAME = os.getenv("WORKIQ_AGENT_NAME", "workiqagent")
AGENT_VERSION = os.getenv("WORKIQ_AGENT_VERSION", "13")

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")

ORCHESTRATOR_INSTRUCTIONS = """
You are the **Magentic-One Manager** for a WorkIQ orchestration built on the
Microsoft Agent Framework. Your participants include a `WorkIQAgent` that can
delegate workplace-productivity questions to the Foundry hosted `workiqagent`
via its `ask_workiq_agent` tool.

Responsibilities:
1. Build a short plan (facts + steps) for the user's task.
2. Drive the conversation by selecting `WorkIQAgent` whenever the task needs
   workplace, knowledge-base, document, or analysis information.
3. Decompose complex requests into multiple sub-queries when helpful.
4. Stop when you have a complete, well-structured final answer for the user.
5. Never fabricate information — only use what participants return.

Be concise, professional, and structured.
""".strip()

WORKIQ_PARTICIPANT_INSTRUCTIONS = """
You are **WorkIQAgent**, a participant in a Magentic-One orchestration.

For any workplace-productivity, knowledge-base, document, or analysis question
the manager assigns to you, you MUST call the `ask_workiq_agent` tool with a
precise sub-query that restates the manager's request. You have no memory of
prior turns; restate the intent clearly each time.

Return the tool's answer back to the manager as your reply. Do not invent
information; if the tool returns nothing useful, say so.
""".strip()


# =============================================================================
# Material Design 3 styles + single-screen layout
# =============================================================================
MD3_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

:root {
    --md-primary:        #0D47A1;
    --md-on-primary:     #FFFFFF;
    --md-primary-cont:   #BBDEFB;
    --md-surface:        #FAFBFE;
    --md-surface-cont:   #FFFFFF;
    --md-surface-high:   #E3F2FD;
    --md-on-surface:     #1C1B1F;
    --md-on-surface-var: #49454F;
    --md-outline:        #90CAF9;
    --md-outline-var:    #E3F2FD;
    --md-secondary:      #1565C0;
    --md-tertiary:       #1976D2;
    --md-success:        #2E7D32;
    --md-warning:        #F57C00;
    --md-error:          #B3261E;
    --md-shadow:         rgba(0,0,0,0.08);
}

html, body, [data-testid="stAppViewContainer"] { overflow: hidden !important; }
.stMainBlockContainer { padding-top: 0.75rem !important; padding-bottom: 0 !important; }

.md3-top-bar {
    background: linear-gradient(135deg,#0D47A1 0%,#1565C0 45%,#1976D2 100%);
    color:#fff; padding:14px 24px; border-radius:0 0 24px 24px;
    margin:-1rem -1rem 0.75rem -1rem;
    box-shadow:0 4px 16px rgba(13,71,161,0.25);
    display:flex; align-items:center; justify-content:space-between; gap:16px;
}
.md3-top-bar h1 { margin:0; font-size:1.35rem; font-weight:600; letter-spacing:-0.01em; }
.md3-top-bar p  { margin:2px 0 0; font-size:0.78rem; opacity:0.85; font-weight:300; }
.md3-top-bar .badge {
    background: rgba(255,255,255,0.18); padding:4px 12px; border-radius:16px;
    font-size:0.72rem; font-weight:500;
}

.md3-section {
    display:flex; align-items:center; gap:8px;
    font-size:0.78rem; font-weight:600; letter-spacing:0.06em;
    text-transform:uppercase; color:var(--md-secondary);
    margin:0 0 6px 4px;
}

.chat-user {
    background: linear-gradient(135deg,#0D47A1,#1565C0); color:#fff;
    padding:10px 14px; border-radius:18px 18px 4px 18px;
    margin:6px 0 6px auto; max-width:88%;
    font-size:0.88rem; line-height:1.5; word-wrap:break-word;
    box-shadow:0 2px 6px rgba(13,71,161,0.22);
}
.chat-assistant {
    background:var(--md-surface-high); color:var(--md-on-surface);
    padding:10px 14px; border-radius:18px 18px 18px 4px;
    margin:6px 0; max-width:88%;
    font-size:0.88rem; line-height:1.5; word-wrap:break-word;
    border:1px solid var(--md-outline);
}
.chat-meta {
    font-size:0.65rem; color:var(--md-on-surface-var);
    opacity:0.75; margin:-2px 4px 6px 4px;
}

.md3-chip {
    display:inline-flex; align-items:center; gap:5px;
    background:var(--md-surface-high); border:1px solid var(--md-outline);
    padding:4px 11px; border-radius:18px;
    font-size:0.75rem; font-weight:500; color:var(--md-on-surface);
    margin:2px 3px;
}
.md3-chip .chip-label { color:var(--md-secondary); font-weight:600; }
.md3-chip.orch { background:#E8F5E9; border-color:#A5D6A7; }
.md3-chip.orch .chip-label { color:var(--md-success); }

.empty {
    text-align:center; color:var(--md-on-surface-var);
    padding:60px 16px; font-size:0.85rem;
}
.empty .icon { font-size:2.4rem; margin-bottom:10px; }

.stChatInput > div {
    border-radius:24px !important;
    border:2px solid var(--md-outline) !important;
    box-shadow:0 2px 10px var(--md-shadow) !important;
}
.stChatInput > div:focus-within {
    border-color:var(--md-primary) !important;
    box-shadow:0 2px 14px rgba(13,71,161,0.18) !important;
}
[data-testid="stExpander"] {
    border:1px solid var(--md-outline) !important;
    border-radius:14px !important;
    box-shadow:0 1px 3px var(--md-shadow) !important;
    margin-bottom:6px !important;
}
::-webkit-scrollbar { width:6px; }
::-webkit-scrollbar-track { background:var(--md-surface-high); border-radius:3px; }
::-webkit-scrollbar-thumb { background:var(--md-outline);    border-radius:3px; }
</style>
"""


# =============================================================================
# Foundry hosted workiqagent — invoked as a tool by the MAF orchestrator
# =============================================================================
def _call_foundry_workiqagent(query: str) -> dict:
    """Call the Foundry hosted ``workiqagent`` via the Responses API
    ``agent_reference`` mechanism. Returns text + per-sub-agent telemetry."""
    out: dict = {
        "query": query,
        "text": "",
        "agent_outputs": [],
        "workflow_steps": [],
        "token_usage": {"input": 0, "output": 0, "total": 0},
        "trace_id": "",
        "debug_logs": [],
    }

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=AZURE_AI_PROJECT, credential=credential)

    with get_tracer().start_as_current_span(
        f"foundry-{AGENT_NAME}", kind=SpanKind.CLIENT
    ) as span:
        out["trace_id"] = format_trace_id(span.get_span_context().trace_id)

        with project_client:
            openai_client = project_client.get_openai_client()
            conversation = openai_client.conversations.create()
            out["debug_logs"].append(f"Conversation created: {conversation.id}")

            stream = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {
                        "name": AGENT_NAME,
                        "type": "agent_reference",
                    }
                },
                input=query,
                stream=True,
                metadata={"x-ms-debug-mode-enabled": "1"},
            )

            current_agent_id: str | None = None
            current_buf: str = ""

            for event in stream:
                etype = getattr(event, "type", "")
                item = getattr(event, "item", None)
                itype = getattr(item, "type", "") if item is not None else ""

                if etype == "response.output_item.added" and itype == "workflow_action":
                    if current_agent_id and current_buf:
                        out["agent_outputs"].append({
                            "agent_id": current_agent_id,
                            "output": current_buf,
                            "status": "in_progress",
                            "ts": datetime.now().strftime("%H:%M:%S"),
                        })
                    current_agent_id = getattr(item, "action_id", "agent")
                    current_buf = ""
                    out["workflow_steps"].append({
                        "action_id": current_agent_id,
                        "status": "started",
                        "ts": datetime.now().strftime("%H:%M:%S"),
                    })

                elif etype == "response.output_item.done" and itype == "workflow_action":
                    action_id = getattr(item, "action_id", current_agent_id or "agent")
                    status = getattr(item, "status", "completed")
                    if current_buf:
                        out["agent_outputs"].append({
                            "agent_id": action_id,
                            "output": current_buf,
                            "status": status,
                            "ts": datetime.now().strftime("%H:%M:%S"),
                        })
                        current_buf = ""
                    out["workflow_steps"].append({
                        "action_id": action_id,
                        "status": status,
                        "ts": datetime.now().strftime("%H:%M:%S"),
                    })
                    out["debug_logs"].append(f"Agent '{action_id}' -> {status}")

                elif etype == "response.output_text.delta":
                    current_buf += getattr(event, "delta", "")

                elif etype == "response.output_text.done":
                    text = getattr(event, "text", "") or ""
                    if text:
                        out["text"] += text + "\n"

                elif etype == "response.completed":
                    resp = getattr(event, "response", None)
                    usage = getattr(resp, "usage", None) if resp else None
                    if usage:
                        out["token_usage"] = {
                            "input": getattr(usage, "input_tokens", 0) or 0,
                            "output": getattr(usage, "output_tokens", 0) or 0,
                            "total": getattr(usage, "total_tokens", 0) or 0,
                        }
                    out["debug_logs"].append("Response completed")

            if current_agent_id and current_buf:
                out["agent_outputs"].append({
                    "agent_id": current_agent_id,
                    "output": current_buf,
                    "status": "completed",
                    "ts": datetime.now().strftime("%H:%M:%S"),
                })

            try:
                openai_client.conversations.delete(conversation_id=conversation.id)
            except Exception as ex:  # noqa: BLE001
                logger.warning("Could not delete conversation %s: %s",
                               conversation.id, ex)

    if not out["text"].strip() and out["agent_outputs"]:
        out["text"] = out["agent_outputs"][-1]["output"]

    return out


# =============================================================================
# MAF Orchestrator — ChatAgent that calls workiqagent as a tool
# =============================================================================
# Per-run accumulator so the tool function can record sub-calls for the UI.
# Streamlit reruns are single-threaded so a module global is safe here.
_RUN_ACCUMULATOR: dict | None = None


def ask_workiq_agent(
    sub_query: Annotated[
        str,
        Field(description=(
            "Precise question to ask the Foundry hosted `workiqagent`. "
            "Restate the user's intent clearly; this agent has no memory of "
            "prior turns in this orchestration."
        )),
    ],
) -> str:
    """Delegate a workplace-productivity question to the Foundry `workiqagent`.

    Use this for any workplace, knowledge-base, document, or analysis
    question. Returns the agent's textual answer.
    """
    logger.info("Orchestrator -> workiqagent: %s", sub_query)
    result = _call_foundry_workiqagent(sub_query)

    if _RUN_ACCUMULATOR is not None:
        _RUN_ACCUMULATOR["foundry_calls"].append(result)
        u = result.get("token_usage", {})
        agg = _RUN_ACCUMULATOR["foundry_token_usage"]
        agg["input"] += u.get("input", 0) or 0
        agg["output"] += u.get("output", 0) or 0
        agg["total"] += u.get("total", 0) or 0

    return result.get("text", "").strip() or "(workiqagent returned no text)"


def _build_orchestrator_client() -> OpenAIChatCompletionClient:
    """Build an Azure OpenAI **Chat Completions** client for orchestrator agents.

    Notes:
      * We deliberately use ``OpenAIChatCompletionClient`` (Chat Completions API),
        not ``OpenAIChatClient`` (Responses API). The Responses API maintains
        server-side conversation state via ``previous_response_id``; when the
        Magentic manager replays the chat history (which already contains tool
        call items) the server complains about duplicates
        (``Duplicate item found with id fc_...``). Chat Completions is
        stateless and is safe to use under group-chat orchestration.
      * Defaults to ``DefaultAzureCredential`` (Entra ID). Set
        ``AZURE_OPENAI_USE_AAD=0`` together with ``AZURE_OPENAI_KEY`` to use
        key-based auth instead.
    """
    use_aad = os.getenv("AZURE_OPENAI_USE_AAD", "1").lower() not in ("0", "false", "no", "")
    kwargs: dict = {}
    if AZURE_OPENAI_ENDPOINT:
        kwargs["azure_endpoint"] = AZURE_OPENAI_ENDPOINT
    if AZURE_OPENAI_DEPLOYMENT:
        kwargs["model"] = AZURE_OPENAI_DEPLOYMENT
    if AZURE_OPENAI_KEY and not use_aad:
        kwargs["api_key"] = AZURE_OPENAI_KEY
    else:
        kwargs["credential"] = DefaultAzureCredential()
    return OpenAIChatCompletionClient(**kwargs)


async def run_orchestrator_async(user_query: str) -> dict:
    """Run a Magentic-One orchestration where the manager coordinates a
    `WorkIQAgent` participant that calls the Foundry hosted ``workiqagent``
    via its tool.
    """
    global _RUN_ACCUMULATOR
    _RUN_ACCUMULATOR = {
        "foundry_calls": [],
        "foundry_token_usage": {"input": 0, "output": 0, "total": 0},
    }
    orchestrator_events: list[dict] = []

    with get_tracer().start_as_current_span(
        "MAF-MagenticOne-WorkIQ", kind=SpanKind.CLIENT
    ) as span:
        trace_id = format_trace_id(span.get_span_context().trace_id)

        # Each agent gets its OWN chat client instance to keep their
        # session/state strictly isolated.
        participant_client = _build_orchestrator_client()
        manager_client = _build_orchestrator_client()

        # Participant: WorkIQAgent — exposes the foundry workiqagent as a tool
        workiq_agent = Agent(
            client=participant_client,
            instructions=WORKIQ_PARTICIPANT_INSTRUCTIONS,
            name="WorkIQAgent",
            description=(
                "Specialist that answers workplace-productivity, knowledge-base, "
                "document, and analysis questions by delegating to the Foundry "
                "hosted `workiqagent` via the `ask_workiq_agent` tool."
            ),
            tools=ask_workiq_agent,
        )

        # Manager: Magentic-One standard manager driven by an LLM agent
        manager_agent = Agent(
            client=manager_client,
            instructions=ORCHESTRATOR_INSTRUCTIONS,
            name="MagenticManager",
        )
        manager = StandardMagenticManager(
            agent=manager_agent,
            max_round_count=8,
            max_stall_count=2,
        )

        workflow = MagenticBuilder(
            participants=[workiq_agent],
            manager=manager,
            intermediate_outputs=True,
        ).build()

        # Stream events so we can capture orchestrator activity for the UI
        stream = workflow.run(user_query, stream=True)
        async for event in stream:
            if isinstance(event, MagenticOrchestratorEvent):
                orchestrator_events.append({
                    "kind": getattr(event, "event_type", str(type(event).__name__)),
                    "detail": str(getattr(event, "message", event)),
                    "ts": datetime.now().strftime("%H:%M:%S"),
                })
        result = await stream.get_final_response()

    # Pull the final assistant text from the workflow outputs
    final_text = ""
    try:
        outputs = result.get_outputs()
        for o in outputs:
            if o is None:
                continue
            final_text += str(o)
            if not final_text.endswith("\n"):
                final_text += "\n"
    except Exception:  # noqa: BLE001
        final_text = str(result)

    run = {
        "final_response": final_text.strip(),
        "trace_id": trace_id,
        "orchestrator_agent": "MagenticOne (manager + WorkIQAgent)",
        "orchestrator_model": AZURE_OPENAI_DEPLOYMENT or "azure-openai",
        "foundry_calls": _RUN_ACCUMULATOR["foundry_calls"],
        "foundry_token_usage": _RUN_ACCUMULATOR["foundry_token_usage"],
        "orchestrator_events": orchestrator_events,
    }
    _RUN_ACCUMULATOR = None
    return run


def run_orchestrator(user_query: str) -> dict:
    """Sync wrapper for use in Streamlit's main thread."""
    return asyncio.run(run_orchestrator_async(user_query))


# =============================================================================
# Streamlit UI
# =============================================================================
def _esc(s: str) -> str:
    return (s or "").replace("<", "&lt;").replace(">", "&gt;")


def _render_chat_history():
    if not st.session_state.messages:
        st.markdown(
            '<div class="empty"><div class="icon">💬</div>'
            '<div><b>Start a conversation</b></div>'
            '<p>The MAF orchestrator will route your question to <code>workiqagent</code>.</p></div>',
            unsafe_allow_html=True,
        )
        return
    for msg in st.session_state.messages:
        role = msg["role"]
        ts = msg.get("ts", "")
        content = _esc(msg["content"])
        if role == "user":
            st.markdown(f'<div class="chat-user">{content}</div>', unsafe_allow_html=True)
            if ts:
                st.markdown(
                    f'<div class="chat-meta" style="text-align:right;">{ts}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(f'<div class="chat-assistant">{content}</div>', unsafe_allow_html=True)
            if ts:
                st.markdown(f'<div class="chat-meta">{ts}</div>', unsafe_allow_html=True)


def _render_agent_panel():
    if not st.session_state.agent_runs:
        st.markdown(
            '<div class="empty"><div class="icon">🤖</div>'
            '<div><b>No agent runs yet</b></div>'
            '<p>Per-agent outputs and token usage will appear here.</p></div>',
            unsafe_allow_html=True,
        )
        return

    for idx, run in enumerate(reversed(st.session_state.agent_runs)):
        run_no = len(st.session_state.agent_runs) - idx
        usage = run.get("foundry_token_usage", {})
        foundry_calls = run.get("foundry_calls", [])

        st.markdown(
            f'<div class="md3-section">▸ Run #{run_no} · '
            f'{_esc(run.get("query_preview",""))}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div>'
            f'<span class="md3-chip orch">🧭 Orchestrator '
            f'<span class="chip-label">{_esc(run.get("orchestrator_agent",""))}</span></span>'
            f'<span class="md3-chip orch">🤖 Model '
            f'<span class="chip-label">{_esc(run.get("orchestrator_model",""))}</span></span>'
            f'<span class="md3-chip">🧩 workiqagent calls '
            f'<span class="chip-label">{len(foundry_calls)}</span></span>'
            f'<span class="md3-chip">📥 Input '
            f'<span class="chip-label">{usage.get("input",0)}</span></span>'
            f'<span class="md3-chip">📤 Output '
            f'<span class="chip-label">{usage.get("output",0)}</span></span>'
            f'<span class="md3-chip">📊 Total '
            f'<span class="chip-label">{usage.get("total",0)}</span></span>'
            f'<span class="md3-chip">🔗 Trace '
            f'<span class="chip-label">{_esc(run.get("trace_id","")[:12])}…</span></span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        if not foundry_calls:
            st.caption("Manager did not delegate to WorkIQAgent for this turn.")

        # Magentic-One orchestrator events
        orch_events = run.get("orchestrator_events", [])
        if orch_events:
            with st.expander(
                f"🧭 Magentic-One orchestrator events ({len(orch_events)})",
                expanded=False,
            ):
                for ev in orch_events:
                    st.write(
                        f"• **{ev.get('kind','event')}** — "
                        f"_{ev.get('ts','')}_ — {_esc(ev.get('detail',''))[:300]}"
                    )

        for ci, call in enumerate(foundry_calls, 1):
            ctu = call.get("token_usage", {})
            label = (
                f"🛰 Foundry call #{ci} · workiqagent · "
                f"in {ctu.get('input',0)} / out {ctu.get('output',0)} / "
                f"total {ctu.get('total',0)}"
            )
            with st.expander(label, expanded=(ci == 1 and idx == 0)):
                st.markdown(f"**Sub-query:** _{_esc(call.get('query',''))}_")
                st.markdown("**workiqagent response:**")
                st.markdown(call.get("text", "") or "_(no text)_")

                inner = call.get("agent_outputs", [])
                if inner:
                    st.markdown("**Internal agents:**")
                    for ao in inner:
                        with st.expander(
                            f"🧩 {ao.get('agent_id','agent')} · "
                            f"{ao.get('status','')} · {ao.get('ts','')}",
                            expanded=False,
                        ):
                            st.markdown(ao.get("output", "") or "_(no text)_")

                steps = call.get("workflow_steps", [])
                if steps:
                    with st.expander(f"🛠 Workflow steps ({len(steps)})", expanded=False):
                        for s in steps:
                            st.write(
                                f"• **{s.get('action_id','')}** — "
                                f"{s.get('status','')} _({s.get('ts','')})_"
                            )

                logs = call.get("debug_logs", [])
                if logs:
                    with st.expander(f"🪵 Debug log ({len(logs)})", expanded=False):
                        st.code("\n".join(logs), language="text")

        st.markdown(
            '<div style="height:1px;background:var(--md-outline-var);margin:10px 0;"></div>',
            unsafe_allow_html=True,
        )


def main() -> None:
    st.set_page_config(
        page_title="WorkIQ · MAF Orchestrator",
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(MD3_CSS, unsafe_allow_html=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "agent_runs" not in st.session_state:
        st.session_state.agent_runs = []

    st.markdown(
        f"""
        <div class="md3-top-bar">
            <div>
                <h1>🧭 WorkIQ Orchestrator · Microsoft Agent Framework</h1>
                <p>MAF <code>ChatAgent</code> → tool → Foundry hosted
                   <code>{AGENT_NAME}</code> · DefaultAzureCredential</p>
            </div>
            <div class="badge">v{AGENT_VERSION}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([1, 1], gap="medium")

    with col_left:
        st.markdown('<div class="md3-section">💬 Conversation History</div>',
                    unsafe_allow_html=True)
        chat_box = st.container(height=500, border=True)
        with chat_box:
            _render_chat_history()

    with col_right:
        st.markdown(
            '<div class="md3-section">🤖 Orchestrator &amp; workiqagent Outputs</div>',
            unsafe_allow_html=True,
        )
        agent_box = st.container(height=500, border=True)
        with agent_box:
            _render_agent_panel()

    prompt = st.chat_input("Ask the WorkIQ orchestrator…")
    if prompt:
        ts = datetime.now().strftime("%H:%M:%S")
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "ts": ts}
        )

        try:
            with st.spinner("🔄 Orchestrator planning & invoking workiqagent…",
                            show_time=True):
                result = run_orchestrator(prompt)
        except Exception as ex:  # noqa: BLE001
            logger.exception("Orchestrator failed")
            st.session_state.messages.append({
                "role": "assistant",
                "content": f"⚠️ Orchestrator error: `{ex}`",
                "ts": datetime.now().strftime("%H:%M:%S"),
            })
            st.rerun()
            return

        st.session_state.messages.append({
            "role": "assistant",
            "content": result.get("final_response", "").strip() or "_(no response)_",
            "ts": datetime.now().strftime("%H:%M:%S"),
        })
        result["query_preview"] = (prompt[:40] + "…") if len(prompt) > 40 else prompt
        st.session_state.agent_runs.append(result)
        st.rerun()


if __name__ == "__main__":
    main()
