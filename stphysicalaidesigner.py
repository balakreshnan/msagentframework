# Copyright (c) Microsoft. All rights reserved.
"""
Physical AI Designer — Streamlit app powered by Microsoft Agent Framework
Magentic orchestration over 3 specialist Foundry agents:

    1. Strategist & Requirements Agent  (Planner / Orchestrator role)
    2. Scene & Simulation Designer Agent (Omniverse / Isaac Sim / synthetic data)
    3. Training & Implementation Engineer Agent (GR00T / Isaac Lab / Jetson deploy)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time as _time
import traceback
from datetime import datetime
from typing import cast

import streamlit as st
from dotenv import load_dotenv

from agent_framework import Agent, AgentResponseUpdate, Message, WorkflowEvent
from agent_framework.foundry import FoundryChatClient
from agent_framework.orchestrations import (
    GroupChatRequestSentEvent,
    MagenticBuilder,
    MagenticProgressLedger,
    StandardMagenticManager,
)
from azure.identity import DefaultAzureCredential

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("stphysicalaidesigner")

load_dotenv()

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
MODEL_DEPLOYMENT = os.getenv(
    "AZURE_AI_MODEL_DEPLOYMENT_NAME_AGENT",
    os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini"),
)

# ============================================================================
# AGENT DEFINITIONS  (instructions used by each FoundryAgent)
# ============================================================================
STRATEGIST_NAME = "StrategistRequirementsAgent"
SCENE_NAME = "SceneSimulationDesignerAgent"
TRAINING_NAME = "TrainingImplementationEngineerAgent"

STRATEGIST_INSTRUCTIONS = """You are the **Strategist & Requirements Agent** for a Physical AI design team.
Your job is high-level analysis and planning. Produce concise, structured output:

1. **Use case breakdown** — restate the problem, target environment, robot/embodiment, KPIs.
2. **Stakeholders & constraints** — safety, regulatory, latency, hardware budget.
3. **Functional & non-functional requirements** — perception, planning, control, HMI.
4. **High-level architecture** — sensors → perception → policy → actuation pipeline.
5. **Success criteria & milestones** — measurable acceptance gates.

Keep the response under 1200 tokens. Use Markdown headings and bullet lists.
Do NOT write code. Do NOT design scenes. Hand off to the Scene & Simulation Designer.
"""

SCENE_INSTRUCTIONS = """You are the **Scene & Simulation Designer Agent**.
Given the strategist's requirements, design the simulation foundation:

1. **Asset ingestion plan** — CAD/USD/photo sources, scale, units, materials.
2. **3D scene reconstruction** — environment layout, lighting, physics colliders.
3. **Simulation setup** — recommend NVIDIA Omniverse / Isaac Sim configuration
   (extensions, RTX render settings, domain randomization knobs).
4. **Synthetic data generation** — Replicator pipelines, randomization ranges,
   ground-truth annotations (bbox, segmentation, depth, pose).
5. **Validation strategy** — sim-to-real gap checks, dataset balance.

Keep under 1200 tokens. Use Markdown. Reference concrete Isaac Sim / Replicator
APIs when helpful, but do NOT produce training code — leave that to the Training
& Implementation Engineer.
"""

TRAINING_INSTRUCTIONS = """You are the **Training & Implementation Engineer Agent**.
Using the strategist's plan and the scene designer's simulation output, deliver
the implementation blueprint:

1. **Model selection / fine-tuning** — recommend a foundation policy (e.g. NVIDIA
   GR00T N1, Isaac Lab RL policies, VLA models) with rationale.
2. **Training pipeline** — dataset loading, curriculum, hyperparameters, eval.
3. **Code scaffolding** — provide a short Python skeleton (Isaac Lab / PyTorch)
   that another engineer can extend. Keep code blocks compact.
4. **Deployment** — packaging for NVIDIA Jetson (Orin / Thor), TensorRT export,
   ROS 2 integration, runtime telemetry.
5. **End-to-end pipeline** — describe the CI loop: sim data → train → eval → OTA.

Keep under 1500 tokens. Use Markdown. This is the FINAL agent in the workflow —
end with a one-paragraph executive summary suitable for the strategist's report.
"""

MANAGER_INSTRUCTIONS = f"""You are the Magentic Manager for a Physical AI design team.
Your ONLY job is to route messages to agents in a fixed sequence. Do NOT generate content yourself.

SEQUENCE (call each agent EXACTLY ONCE in this order):
1. {STRATEGIST_NAME} → Strategy, requirements, high-level architecture
2. {SCENE_NAME} → Scene assets, Isaac Sim setup, synthetic data plan
3. {TRAINING_NAME} → Model selection, training, Jetson deployment, code

RULES:
- Use the EXACT agent names listed above when selecting the next speaker.
- Call each agent exactly once. Never skip, repeat, or reorder.
- Pass accumulated context from all previous agents to the next.
- After {TRAINING_NAME} responds, mark the request as satisfied and TERMINATE.
- Do NOT ask for revisions, feedback, or additional rounds.
- Never generate harmful, illegal, or PII-related content.

Start now: send the user's task to {STRATEGIST_NAME}.
"""

AGENT_META = {
    STRATEGIST_NAME: {"icon": "🧭", "label": "Strategist & Requirements"},
    SCENE_NAME: {"icon": "🏗️", "label": "Scene & Simulation Designer"},
    TRAINING_NAME: {"icon": "🤖", "label": "Training & Implementation Engineer"},
}

# ============================================================================
# UI STYLES — modern, light, single-viewport
# ============================================================================
APP_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, sans-serif; }
#MainMenu, footer, header { visibility: hidden; }
.stDeployButton { display: none; }

.block-container {
    padding-top: 0.4rem !important;
    padding-bottom: 0.4rem !important;
    max-width: 100% !important;
}
[data-testid="stVerticalBlock"] { gap: 0.35rem !important; }
section.main > div { padding-top: 0 !important; }
.stExpander { margin-bottom: 0.2rem !important; }
.stExpander details summary {
    padding: 0.3rem 0.55rem !important;
    font-size: 0.84rem !important;
}
.stTabs [data-baseweb="tab-list"] { gap: 4px !important; margin-bottom: 4px !important; }
.stTabs [data-baseweb="tab"] { padding: 4px 10px !important; font-size: 0.78rem !important; }
[data-testid="stMetricValue"] { font-size: 1.05rem !important; }
[data-testid="stMetricLabel"] { font-size: 0.7rem !important; }

:root {
    --pad-primary:  #5B8DEF;
    --pad-accent:   #7C5CFF;
    --pad-mint:     #34D1BF;
    --pad-bg:       #F7F9FC;
    --pad-card:     #FFFFFF;
    --pad-ink:      #1F2433;
    --pad-soft:     #6B7280;
    --pad-line:     #E6EAF2;
}

body { background: var(--pad-bg); }

.pad-topbar {
    background: linear-gradient(120deg, #5B8DEF 0%, #7C5CFF 55%, #34D1BF 100%);
    color: #fff;
    padding: 8px 18px;
    border-radius: 0 0 16px 16px;
    margin: -0.4rem -1rem 0.5rem -1rem;
    box-shadow: 0 6px 20px rgba(91,141,239,0.25);
}
.pad-topbar h1 { margin: 0; font-size: 1.05rem; font-weight: 600; letter-spacing: -0.01em; }
.pad-topbar p  { margin: 2px 0 0 0; font-size: 0.7rem; opacity: 0.92; font-weight: 300; }

.pad-label {
    font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.12em; color: var(--pad-accent);
    margin: 2px 0 4px 2px;
}

.pad-chip {
    display: inline-block;
    background: #fff;
    color: var(--pad-ink);
    border: 1px solid var(--pad-line);
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 500;
    margin-right: 4px;
}

.chat-bubble-user {
    background: linear-gradient(135deg, #5B8DEF 0%, #7C5CFF 100%);
    color: #fff;
    padding: 8px 12px;
    border-radius: 16px 16px 4px 16px;
    margin: 4px 0 2px auto;
    max-width: 88%;
    font-size: 0.84rem;
    line-height: 1.4;
    width: fit-content;
    box-shadow: 0 2px 8px rgba(91,141,239,0.2);
}
.chat-bubble-assistant {
    background: #fff;
    color: var(--pad-ink);
    padding: 8px 12px;
    border-radius: 16px 16px 16px 4px;
    margin: 4px auto 2px 0;
    max-width: 95%;
    font-size: 0.84rem;
    line-height: 1.45;
    border: 1px solid var(--pad-line);
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.chat-timestamp {
    font-size: 0.62rem; color: var(--pad-soft);
    margin: 0 4px 6px 4px;
}

.empty-state {
    text-align: center; padding: 24px 12px; color: var(--pad-soft);
}
.empty-state .icon { font-size: 2.4rem; margin-bottom: 6px; }
.empty-state h3 { margin: 4px 0; color: var(--pad-ink); font-size: 0.95rem; }
.empty-state p  { font-size: 0.78rem; margin: 2px 0; }

div[data-testid="stProgress"] > div > div > div > div {
    background: linear-gradient(90deg, #5B8DEF 0%, #7C5CFF 50%, #34D1BF 100%) !important;
}
</style>
"""


# ============================================================================
# WORKFLOW
# ============================================================================
async def run_physical_ai_workflow(task: str, ui_hooks: dict | None = None) -> dict:
    """Run the 3-agent Magentic workflow and stream events back to the UI."""
    result: dict = {
        "summary": "",
        "agent_outputs": [],
        "planner_updates": [],
        "debug_logs": [],
        "token_usage": {
            "total": {"input_token_count": 0, "output_token_count": 0, "total_token_count": 0},
            "by_agent": {},
            "events": 0,
        },
        "elapsed_seconds": 0.0,
        "error": None,
    }

    # ----- helpers ---------------------------------------------------------
    def _accumulate_usage(agent_name: str, usage):
        if not usage:
            return

        def _read(src, *names):
            for n in names:
                if hasattr(src, n):
                    v = getattr(src, n)
                    if v is not None:
                        try:
                            return int(v)
                        except Exception:
                            pass
                if isinstance(src, dict) and src.get(n) is not None:
                    try:
                        return int(src[n])
                    except Exception:
                        pass
            return 0

        inp = _read(usage, "input_token_count", "prompt_tokens", "input_tokens")
        out = _read(usage, "output_token_count", "completion_tokens", "output_tokens")
        tot = _read(usage, "total_token_count", "total_tokens") or (inp + out)
        if inp == 0 and out == 0 and tot == 0:
            return
        tu = result["token_usage"]
        tu["events"] += 1
        tu["total"]["input_token_count"] += inp
        tu["total"]["output_token_count"] += out
        tu["total"]["total_token_count"] += tot
        ag = tu["by_agent"].setdefault(
            agent_name,
            {"input_token_count": 0, "output_token_count": 0, "total_token_count": 0},
        )
        ag["input_token_count"] += inp
        ag["output_token_count"] += out
        ag["total_token_count"] += tot

    def _harvest_usage(agent_name: str, obj):
        """Recursively walk an object/dict tree to find any usage payload."""
        if obj is None:
            return
        seen: set[int] = set()

        def _try(node, depth: int = 0):
            if node is None or depth > 4:
                return
            nid = id(node)
            if nid in seen:
                return
            seen.add(nid)

            # 1) direct usage-like attr/dict on this node
            for key in ("usage_details", "usage", "token_usage", "usageDetails"):
                val = None
                if hasattr(node, key):
                    val = getattr(node, key, None)
                elif isinstance(node, dict) and key in node:
                    val = node.get(key)
                if val is not None:
                    _accumulate_usage(agent_name, val)

            # 2) recurse into common containers that may wrap a run/step
            for key in (
                "raw_representation", "raw_response", "response", "run",
                "run_step", "step", "step_details", "contents", "content",
                "messages", "choices", "data",
            ):
                child = None
                if hasattr(node, key):
                    child = getattr(node, key, None)
                elif isinstance(node, dict) and key in node:
                    child = node.get(key)
                if isinstance(child, (list, tuple)):
                    for c in child:
                        _try(c, depth + 1)
                elif child is not None:
                    _try(child, depth + 1)

        try:
            _try(obj)
        except Exception as e:
            result["debug_logs"].append(f"[token usage] harvest error: {e}")

    # ----- live UI updaters -----------------------------------------------
    def _update_agents():
        if not (ui_hooks and ui_hooks.get("agent_container")):
            return
        ph = ui_hooks["agent_container"]
        with ph.container():
            seen = {}
            for ab in result["agent_outputs"]:
                if (ab.get("text") or "").strip():
                    seen[ab["agent"]] = ab
            visible = list(seen.values())
            for i, ab in enumerate(visible):
                meta = AGENT_META.get(ab["agent"], {"icon": "🟢", "label": ab["agent"]})
                with st.expander(
                    f"{meta['icon']} {meta['label']}",
                    expanded=(i == len(visible) - 1),
                ):
                    st.markdown(ab["text"])

    def _update_progress():
        if not (ui_hooks and ui_hooks.get("progress_bar")):
            return
        completed = sum(
            1 for ab in result["agent_outputs"]
            if (ab.get("text") or "").strip() and not ab.get("_streaming")
        )
        total = len(AGENT_META)
        pct = min(1.0, completed / total)
        elapsed = _time.time() - _workflow_start_time
        ui_hooks["progress_bar"].progress(
            pct, text=f"{completed}/{total} agents complete · {elapsed:0.1f}s"
        )

    def _update_planner():
        if not (ui_hooks and ui_hooks.get("planner_container")):
            return
        ph = ui_hooks["planner_container"]
        plans = [p for p in result["planner_updates"] if p.get("kind") == "plan"]
        ledgers = [p for p in result["planner_updates"] if p.get("kind") == "ledger"]
        with ph.container():
            if not plans:
                st.caption("Waiting for planner output…")
            else:
                for i, p in enumerate(plans):
                    with st.expander(
                        f"📝 Plan #{i + 1}",
                        expanded=(i == len(plans) - 1),
                    ):
                        st.markdown(p.get("text", "_(empty)_"))
            if ledgers:
                st.markdown("---")
                st.caption(f"📒 {len(ledgers)} ledger update(s) — see Ledger tab.")

    def _update_ledger():
        if not (ui_hooks and ui_hooks.get("ledger_container")):
            return
        ph = ui_hooks["ledger_container"]
        ledgers = [p for p in result["planner_updates"] if p.get("kind") == "ledger"]
        with ph.container():
            if not ledgers:
                st.caption("Waiting for progress ledger…")
                return
            for i, l in enumerate(ledgers):
                ledger = l.get("ledger", {}) or {}
                def _f(v):
                    return v.get("answer", v) if isinstance(v, dict) else v
                with st.expander(
                    f"📒 Ledger #{i + 1}",
                    expanded=(i == len(ledgers) - 1),
                ):
                    task_v = _f(ledger.get("task"))
                    prog_v = _f(ledger.get("progress"))
                    next_v = _f(ledger.get("next_speaker"))
                    inst_v = _f(ledger.get("instruction_or_question"))
                    done_v = _f(ledger.get("is_request_satisfied"))
                    if task_v: st.markdown(f"**Task:** {task_v}")
                    if prog_v: st.markdown(f"**Progress:** {prog_v}")
                    if next_v: st.markdown(f"**Next Speaker:** `{next_v}`")
                    if inst_v: st.markdown(f"**Instruction:** {inst_v}")
                    if done_v is not None: st.markdown(f"**Request Satisfied:** {done_v}")
                    with st.popover("📄 Raw JSON"):
                        st.json(ledger)

    # ----- build workflow --------------------------------------------------
    _workflow_start_time = _time.time()

    if not PROJECT_ENDPOINT:
        result["error"] = "AZURE_AI_PROJECT_ENDPOINT is not set in the environment."
        return result

    cred = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=PROJECT_ENDPOINT,
        model=MODEL_DEPLOYMENT,
        credential=cred,
    )

    strategist = Agent(
        name=STRATEGIST_NAME,
        description="Planner/Orchestrator: use case breakdown, requirements, high-level architecture.",
        instructions=STRATEGIST_INSTRUCTIONS,
        client=client,
    )
    scene = Agent(
        name=SCENE_NAME,
        description="3D scene/simulation designer for Omniverse / Isaac Sim & synthetic data.",
        instructions=SCENE_INSTRUCTIONS,
        client=client,
    )
    training = Agent(
        name=TRAINING_NAME,
        description="Model selection, fine-tuning, code generation, Jetson deployment.",
        instructions=TRAINING_INSTRUCTIONS,
        client=client,
    )

    manager_agent = Agent(
        name="MagenticManager",
        description="Routes messages between the 3 Physical AI design specialists in a fixed sequence.",
        instructions=MANAGER_INSTRUCTIONS,
        client=client,
    )

    # Custom plan prompt that FORCES all 3 specialists to be called in order.
    PLAN_PROMPT = (
        "You are creating the plan for a Physical AI design team.\n"
        "You MUST plan to call EACH of the following specialists exactly once, in this order:\n"
        f"  1. {STRATEGIST_NAME} — strategy, requirements, high-level architecture\n"
        f"  2. {SCENE_NAME} — 3D scene, Isaac Sim setup, synthetic data\n"
        f"  3. {TRAINING_NAME} — model selection, training, Jetson deployment, code\n"
        "The request is NOT satisfied until ALL three have produced output.\n"
        "Do NOT skip, repeat, or reorder. Output the plan as a numbered list.\n"
    )

    manager = StandardMagenticManager(
        agent=manager_agent,
        task_ledger_plan_prompt=PLAN_PROMPT,
        max_round_count=20,
        max_stall_count=5,
        max_reset_count=2,
    )

    workflow = MagenticBuilder(
        participants=[strategist, scene, training],
        intermediate_outputs=True,
        manager=manager,
        max_round_count=20,
        max_stall_count=5,
    ).build()

    # Wrap the task with an explicit reminder so the planner LLM produces
    # a plan that hits every specialist.
    augmented_task = (
        f"{task}\n\n"
        "REQUIREMENT: deliver a complete physical-AI design that includes "
        "(1) strategy/requirements, (2) scene & simulation design, and "
        "(3) training & deployment. All three areas are mandatory."
    )

    last_response_id: str | None = None
    output_event: WorkflowEvent | None = None
    current_agent_text = ""
    current_agent_name = ""
    transitions = 0

    try:
        async for event in workflow.run(augmented_task, stream=True):
            if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
                response_id = event.data.response_id
                if response_id != last_response_id:
                    # finalize previous streaming block
                    for ab in result["agent_outputs"]:
                        if ab.get("_streaming"):
                            ab["text"] = (ab.get("text") or "").strip()
                            ab.pop("_streaming", None)
                    current_agent_name = event.executor_id or "Agent"
                    current_agent_text = ""
                    last_response_id = response_id
                    transitions += 1
                    if transitions > 1:
                        await asyncio.sleep(1)
                    result["debug_logs"].append(
                        f"Agent '{current_agent_name}' started streaming"
                    )

                current_agent_text += str(event.data)
                _harvest_usage(current_agent_name, event.data)

                streaming = [ab for ab in result["agent_outputs"] if ab.get("_streaming")]
                if streaming:
                    streaming[0]["text"] = current_agent_text
                    streaming[0]["agent"] = current_agent_name
                else:
                    result["agent_outputs"].append({
                        "agent": current_agent_name,
                        "text": current_agent_text,
                        "_streaming": True,
                    })
                _update_agents()
                _update_progress()

            elif event.type == "magentic_orchestrator":
                evt_name = event.data.event_type.name
                if isinstance(event.data.content, Message):
                    plan_text = event.data.content.text
                    existing_plans = [p for p in result["planner_updates"] if p.get("kind") == "plan"]
                    last_plan_text = (existing_plans[-1].get("text", "") if existing_plans else "").strip()
                    if plan_text.strip() != last_plan_text:
                        result["planner_updates"].append({
                            "event": evt_name, "kind": "plan", "text": plan_text,
                        })
                        _update_planner()
                    result["debug_logs"].append(
                        f"[Orchestrator {evt_name}] {plan_text[:160]}"
                    )
                elif isinstance(event.data.content, MagenticProgressLedger):
                    ledger_dict = event.data.content.to_dict()
                    existing_ledgers = [p for p in result["planner_updates"] if p.get("kind") == "ledger"]
                    last_ledger = existing_ledgers[-1].get("ledger", {}) if existing_ledgers else {}
                    if ledger_dict != last_ledger:
                        result["planner_updates"].append({
                            "event": evt_name, "kind": "ledger", "ledger": ledger_dict,
                        })
                        _update_ledger()
                    result["debug_logs"].append(
                        f"[Orchestrator {evt_name}] ledger update"
                    )

            elif event.type == "group_chat" and isinstance(event.data, GroupChatRequestSentEvent):
                result["debug_logs"].append(
                    f"[Round {event.data.round_index}] → {event.data.participant_name}"
                )

            elif event.type == "output":
                output_event = event

    except Exception as exc:
        elapsed = _time.time() - _workflow_start_time
        tb = traceback.format_exc()
        result["error"] = f"{type(exc).__name__}: {exc}\n\n```\n{tb}\n```"
        result["debug_logs"].append(f"[ERROR @ {elapsed:.1f}s] {exc}")

    # finalize streaming flags
    for ab in result["agent_outputs"]:
        ab.pop("_streaming", None)

    # dedupe by agent name (keep last)
    seen = {}
    for ab in result["agent_outputs"]:
        if (ab.get("text") or "").strip():
            seen[ab["agent"]] = ab
    result["agent_outputs"] = list(seen.values())

    # build final summary from output_event if available
    if output_event:
        parts = []
        outputs = cast(list[Message], output_event.data)
        for message in outputs:
            author = message.author_name or message.role
            meta = AGENT_META.get(str(author), {"icon": "🟢", "label": str(author)})
            parts.append(f"**{meta['icon']} {meta['label']}**\n\n{message.text}")
            _harvest_usage(str(author), message)
        result["summary"] = "\n\n---\n\n".join(parts)
    else:
        # fall back to concatenated agent outputs
        parts = []
        for ab in result["agent_outputs"]:
            meta = AGENT_META.get(ab["agent"], {"icon": "🟢", "label": ab["agent"]})
            parts.append(f"**{meta['icon']} {meta['label']}**\n\n{ab['text']}")
        result["summary"] = "\n\n---\n\n".join(parts) or "_(no output produced)_"

    result["elapsed_seconds"] = round(_time.time() - _workflow_start_time, 2)
    _update_agents()
    _update_progress()
    _update_planner()
    _update_ledger()
    return result


def run_workflow_sync(task: str, ui_hooks: dict | None = None) -> dict:
    return asyncio.run(run_physical_ai_workflow(task, ui_hooks=ui_hooks))


# ============================================================================
# STREAMLIT UI
# ============================================================================
def main():
    st.set_page_config(
        page_title="Physical AI Designer",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(APP_CSS, unsafe_allow_html=True)

    st.markdown(
        """
        <div class="pad-topbar">
            <h1>🤖 Physical AI Designer</h1>
            <p>Magentic orchestration over Strategist · Scene/Sim Designer · Training Engineer — powered by Microsoft Foundry &amp; Agent Framework</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── session defaults ──
    defaults = {
        "messages": [],
        "agent_outputs": [],
        "planner_updates": [],
        "debug_logs": [],
        "token_usage": {
            "total": {"input_token_count": 0, "output_token_count": 0, "total_token_count": 0},
            "by_agent": {},
            "events": 0,
        },
        "elapsed_seconds": 0.0,
        "error_log": None,
        "total_queries": 0,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    col_left, col_right = st.columns([1, 1], gap="medium")

    # ════════════════════════════════════════════════════════════════════
    # LEFT — conversation history & summarized output
    # ════════════════════════════════════════════════════════════════════
    with col_left:
        st.markdown('<div class="pad-label">💬 Conversation &amp; Summary</div>', unsafe_allow_html=True)
        chat_container = st.container(height=500, border=True)
        with chat_container:
            if not st.session_state.messages:
                st.markdown(
                    """
                    <div class="empty-state">
                        <div class="icon">🤖</div>
                        <h3>Welcome to Physical AI Designer</h3>
                        <p>Describe a robotics or physical-AI use case below.</p>
                        <p style="font-size:0.7rem;">e.g. "Design a warehouse pick-and-place robot using a 6-DOF arm with vision-guided grasping for varied SKUs."</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
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

        st.markdown(
            f'<div style="margin-top:6px;">'
            f'<span class="pad-chip">🔄 Queries: {st.session_state.total_queries}</span>'
            f'<span class="pad-chip">⏱️ Last run: {st.session_state.elapsed_seconds:.1f}s</span>'
            f'<span class="pad-chip">🪙 Tokens: {st.session_state.token_usage["total"]["total_token_count"]:,}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ════════════════════════════════════════════════════════════════════
    # RIGHT — per-agent output + token tab
    # ════════════════════════════════════════════════════════════════════
    with col_right:
        st.markdown('<div class="pad-label">🤖 Agent Outputs &amp; Telemetry</div>', unsafe_allow_html=True)
        right_container = st.container(height=500, border=True)
        with right_container:
            tab_agents, tab_plan, tab_ledger, tab_tokens, tab_debug = st.tabs([
                "🧠 Agents",
                f"📝 Plan ({sum(1 for p in (st.session_state.planner_updates or []) if p.get('kind') == 'plan')})",
                f"📒 Ledger ({sum(1 for p in (st.session_state.planner_updates or []) if p.get('kind') == 'ledger')})",
                f"🪙 Tokens ({st.session_state.token_usage['total']['total_token_count']:,})",
                "🐛 Debug",
            ])

            with tab_agents:
                agent_stream_ph = st.empty()
                with agent_stream_ph.container():
                    seen = {}
                    for ab in (st.session_state.agent_outputs or []):
                        if (ab.get("text") or "").strip():
                            seen[ab["agent"]] = ab
                    visible = list(seen.values())
                    if not visible:
                        st.caption("Each agent's response will appear here as an expander once the workflow runs.")
                    else:
                        for i, ab in enumerate(visible):
                            meta = AGENT_META.get(ab["agent"], {"icon": "🟢", "label": ab["agent"]})
                            with st.expander(
                                f"{meta['icon']} {meta['label']}",
                                expanded=(i == len(visible) - 1),
                            ):
                                st.markdown(ab["text"])

            with tab_plan:
                planner_stream_ph = st.empty()
                with planner_stream_ph.container():
                    plans = [p for p in (st.session_state.planner_updates or []) if p.get("kind") == "plan"]
                    if not plans:
                        st.caption("The orchestrator's plan will appear here once agents start collaborating.")
                    else:
                        for i, p in enumerate(plans):
                            with st.expander(
                                f"📝 Plan #{i + 1}",
                                expanded=(i == len(plans) - 1),
                            ):
                                st.markdown(p.get("text", "") or "_(empty)_")

            with tab_ledger:
                ledger_stream_ph = st.empty()
                with ledger_stream_ph.container():
                    ledgers = [p for p in (st.session_state.planner_updates or []) if p.get("kind") == "ledger"]
                    if not ledgers:
                        st.caption("Progress ledger entries will appear here as the orchestrator iterates.")
                    else:
                        for i, l in enumerate(ledgers):
                            ledger = l.get("ledger", {}) or {}
                            def _f(v):
                                return v.get("answer", v) if isinstance(v, dict) else v
                            with st.expander(
                                f"📒 Ledger #{i + 1}",
                                expanded=(i == len(ledgers) - 1),
                            ):
                                task_v = _f(ledger.get("task"))
                                prog_v = _f(ledger.get("progress"))
                                next_v = _f(ledger.get("next_speaker"))
                                inst_v = _f(ledger.get("instruction_or_question"))
                                done_v = _f(ledger.get("is_request_satisfied"))
                                if task_v: st.markdown(f"**Task:** {task_v}")
                                if prog_v: st.markdown(f"**Progress:** {prog_v}")
                                if next_v: st.markdown(f"**Next Speaker:** `{next_v}`")
                                if inst_v: st.markdown(f"**Instruction:** {inst_v}")
                                if done_v is not None: st.markdown(f"**Request Satisfied:** {done_v}")
                                with st.popover("📄 Raw JSON"):
                                    st.json(ledger)

            with tab_tokens:
                tu = st.session_state.token_usage
                total = tu.get("total", {})
                c1, c2, c3 = st.columns(3)
                c1.metric("Input", f"{total.get('input_token_count', 0):,}")
                c2.metric("Output", f"{total.get('output_token_count', 0):,}")
                c3.metric("Total", f"{total.get('total_token_count', 0):,}")
                by_agent = tu.get("by_agent", {})
                if by_agent:
                    rows = [
                        {
                            "Agent": AGENT_META.get(a, {}).get("label", a),
                            "Input": v["input_token_count"],
                            "Output": v["output_token_count"],
                            "Total": v["total_token_count"],
                        }
                        for a, v in by_agent.items()
                    ]
                    st.dataframe(rows, hide_index=True, width='stretch')
                else:
                    st.caption("Per-agent token usage will appear here.")

            with tab_debug:
                if st.session_state.error_log:
                    with st.expander("🚨 Error", expanded=True):
                        st.markdown(st.session_state.error_log)
                if not st.session_state.debug_logs:
                    st.caption("Orchestrator events appear here.")
                else:
                    st.text("\n".join(st.session_state.debug_logs[-25:]))

    # ════════════════════════════════════════════════════════════════════
    # CHAT INPUT
    # ════════════════════════════════════════════════════════════════════
    user_input = st.chat_input("Describe your physical-AI / robotics use case…")
    if user_input:
        now = datetime.now().strftime("%I:%M %p")
        st.session_state.messages.append(
            {"role": "user", "content": user_input, "timestamp": now}
        )

        progress_holder = st.empty()
        progress_bar = progress_holder.progress(0.0, text="Initializing agents…")

        ui_hooks = {
            "agent_container": agent_stream_ph,
            "planner_container": planner_stream_ph,
            "ledger_container": ledger_stream_ph,
            "progress_bar": progress_bar,
        }

        with st.spinner("Agents are collaborating…", show_time=True):
            result = run_workflow_sync(user_input, ui_hooks=ui_hooks)

        progress_bar.progress(
            1.0,
            text=f"Done · {result['elapsed_seconds']:.1f}s · "
                 f"{result['token_usage']['total']['total_token_count']:,} tokens",
        )

        if result.get("error"):
            st.session_state.error_log = result["error"]
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("summary") or "⚠️ Workflow failed. See Debug tab.",
                "timestamp": datetime.now().strftime("%I:%M %p"),
            })
        else:
            st.session_state.error_log = None
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["summary"],
                "timestamp": datetime.now().strftime("%I:%M %p"),
            })

        st.session_state.agent_outputs = result["agent_outputs"]
        st.session_state.planner_updates = result.get("planner_updates", [])
        st.session_state.debug_logs = result["debug_logs"]
        st.session_state.token_usage = result["token_usage"]
        st.session_state.elapsed_seconds = result["elapsed_seconds"]
        st.session_state.total_queries += 1

        st.rerun()


if __name__ == "__main__":
    main()
