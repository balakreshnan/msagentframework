# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
import html as html_lib
import json
import logging
import os
import re
import threading
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
from agent_framework.azure import AzureOpenAIResponsesClient
from agent_framework.orchestrations import GroupChatRequestSentEvent, MagenticBuilder, MagenticProgressLedger
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework.azure import AzureAIProjectAgentProvider
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from azure.ai.projects import AIProjectClient
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from dotenv import load_dotenv
from datetime import datetime

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

myEndpoint = os.getenv("AZURE_AI_PROJECT")

# ============================================================================
# MATERIAL DESIGN 3 CSS
# ============================================================================
MD3_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display: none;}

:root {
    --md-primary: #1B5E20;
    --md-on-primary: #FFFFFF;
    --md-primary-container: #A5D6A7;
    --md-surface: #FAFDF6;
    --md-surface-container: #FFFFFF;
    --md-surface-high: #F1F8E9;
    --md-on-surface: #1C1B1F;
    --md-on-surface-var: #49454F;
    --md-outline: #C8E6C9;
    --md-secondary: #2E7D32;
    --md-shadow: rgba(0,0,0,0.08);
}

.md3-top-bar {
    background: linear-gradient(135deg, #1B5E20 0%, #2E7D32 50%, #388E3C 100%);
    color: white; padding: 20px 32px;
    border-radius: 0 0 28px 28px;
    margin: -1rem -1rem 1.5rem -1rem;
    box-shadow: 0 4px 16px rgba(27,94,32,0.25);
}
.md3-top-bar h1 { margin: 0; font-size: 1.6rem; font-weight: 600; letter-spacing: -0.02em; }
.md3-top-bar p  { margin: 4px 0 0 0; font-size: 0.85rem; opacity: 0.85; font-weight: 300; }

.md3-label {
    font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--md-secondary);
    margin-bottom: 8px; display: flex; align-items: center; gap: 6px;
}

.chat-bubble-user {
    background: linear-gradient(135deg, #1B5E20, #2E7D32);
    color: white; padding: 14px 20px;
    border-radius: 20px 20px 6px 20px;
    margin: 8px 0; max-width: 85%; margin-left: auto;
    font-size: 0.92rem; line-height: 1.55;
    box-shadow: 0 2px 8px rgba(27,94,32,0.2);
    word-wrap: break-word;
}
.chat-bubble-assistant {
    background: var(--md-surface-high);
    color: var(--md-on-surface); padding: 14px 20px;
    border-radius: 20px 20px 20px 6px;
    margin: 8px 0; max-width: 85%;
    font-size: 0.92rem; line-height: 1.55;
    border: 1px solid var(--md-outline);
    word-wrap: break-word;
}

.chat-timestamp {
    font-size: 0.65rem; color: var(--md-on-surface-var);
    margin-top: 2px; opacity: 0.7;
}

.md3-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--md-surface-high);
    border: 1px solid var(--md-outline);
    padding: 6px 14px; border-radius: 20px;
    font-size: 0.78rem; font-weight: 500;
    color: var(--md-on-surface);
}

.empty-state {
    text-align: center; padding: 60px 20px; color: var(--md-on-surface-var);
}
.empty-state .icon { font-size: 3rem; margin-bottom: 12px; }
.empty-state h3 { margin: 0; font-weight: 500; color: var(--md-on-surface); }
.empty-state p  { font-size: 0.85rem; margin-top: 6px; }

.stChatInput > div {
    border-radius: 28px !important;
    border: 2px solid var(--md-outline) !important;
    box-shadow: 0 2px 8px var(--md-shadow) !important;
}
.stChatInput > div:focus-within {
    border-color: var(--md-primary) !important;
    box-shadow: 0 2px 12px rgba(27,94,32,0.18) !important;
}
.stExpander {
    border: 1px solid var(--md-outline) !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 4px var(--md-shadow) !important;
    margin-bottom: 8px !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px !important;
    border-color: var(--md-outline) !important;
}
</style>
"""


# ============================================================================
# TEXT-TO-SPEECH
# ============================================================================
TTS_VOICES = {
    "alloy": "Alloy \u2014 Neutral, balanced",
    "echo": "Echo \u2014 Deeper, authoritative",
    "fable": "Fable \u2014 Expressive storytelling",
    "onyx": "Onyx \u2014 Deep, confident",
    "nova": "Nova \u2014 Bright, energetic",
    "shimmer": "Shimmer \u2014 Soft, calm",
}


def clean_text_for_tts(text: str) -> str:
    """Strip markdown and non-speech elements from text."""
    text = re.sub(r'\u23f1\ufe0f.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    text = re.sub(r'#{1,6}\s*', '', text)
    text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}(.*?)_{1,3}', r'\1', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{2,}', '\n', text)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def generate_speech(text: str, voice: str = "alloy") -> tuple:
    """Generate speech audio from text using gpt-audio-1.5."""
    openai_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_ad_token_provider=get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        ),
        api_version="2025-01-01-preview",
    )
    clean_text = clean_text_for_tts(text)
    if len(clean_text) > 4000:
        clean_text = clean_text[:4000] + "..."
    response = openai_client.chat.completions.create(
        model="gpt-audio-1.5",
        modalities=["text", "audio"],
        audio={"voice": voice, "format": "wav"},
        messages=[
            {"role": "user", "content": f"Read the following text aloud exactly as written:\n\n{clean_text}"}
        ],
    )
    audio_data = response.choices[0].message.audio
    if audio_data and hasattr(audio_data, 'data'):
        return base64.b64decode(audio_data.data), clean_text
    raise RuntimeError("No audio output returned from gpt-audio-1.5")


def render_tts_player(audio_bytes: bytes, text: str):
    """Render an audio player with playback controls and synchronized text highlighting."""
    audio_b64 = base64.b64encode(audio_bytes).decode()

    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text]

    sentence_spans = ""
    for i, sent in enumerate(sentences):
        escaped = html_lib.escape(sent)
        sentence_spans += f'<span id="sent-{i}" class="tts-sentence">{escaped} </span>'

    player_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', sans-serif; padding: 12px; background: transparent; }
        .tts-controls {
            display: flex; align-items: center; gap: 8px; padding: 10px 14px;
            background: linear-gradient(135deg, #E8F5E9, #C8E6C9); border-radius: 14px;
            margin-bottom: 12px; box-shadow: 0 2px 8px rgba(27,94,32,0.1);
        }
        .tts-btn {
            border: none; background: #1B5E20; color: white; width: 34px; height: 34px;
            border-radius: 50%; cursor: pointer; font-size: 14px; display: flex;
            align-items: center; justify-content: center; transition: all 0.2s;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        }
        .tts-btn:hover { background: #2E7D32; transform: scale(1.1); }
        .tts-btn:active { transform: scale(0.95); }
        .tts-progress-wrap {
            flex: 1; height: 8px; background: rgba(255,255,255,0.7); border-radius: 4px;
            cursor: pointer; position: relative; overflow: hidden;
        }
        .tts-progress-fill {
            height: 100%; background: linear-gradient(90deg, #1B5E20, #4CAF50);
            border-radius: 4px; width: 0%; transition: width 0.15s linear;
        }
        .tts-time { font-size: 11px; color: #49454F; min-width: 75px; text-align: right; font-weight: 500; }
        .tts-status { font-size: 11px; color: #1B5E20; font-weight: 600; min-width: 60px; }
        .tts-text-details {
            margin-top: 10px; border: 1px solid #C8E6C9; border-radius: 14px;
            overflow: hidden; background: #FAFDF6;
        }
        .tts-text-details summary {
            padding: 10px 16px; cursor: pointer; font-size: 12.5px; font-weight: 600;
            color: #1B5E20; background: #E8F5E9; user-select: none;
            list-style: none; display: flex; align-items: center; gap: 6px;
        }
        .tts-text-details summary::-webkit-details-marker { display: none; }
        .tts-text-details summary::before { content: '\25b6'; font-size: 10px; transition: transform 0.2s; }
        .tts-text-details[open] summary::before { transform: rotate(90deg); }
        .tts-text-container {
            padding: 14px 16px; line-height: 1.9; font-size: 13.5px; color: #1C1B1F;
            max-height: 300px; overflow-y: auto; scroll-behavior: smooth;
        }
        .tts-sentence { padding: 1px 2px; border-radius: 4px; transition: background-color 0.3s ease, color 0.3s ease; }
        .tts-sentence.active {
            background: linear-gradient(135deg, #A5D6A7, #81C784);
            padding: 2px 4px; border-radius: 6px; font-weight: 500;
        }
        .tts-sentence.spoken { color: #78909C; }
    </style>
    </head>
    <body>
        <div class="tts-controls">
            <button class="tts-btn" onclick="ttsRestart()" title="Restart">&#x23EE;</button>
            <button class="tts-btn" id="tts-play-btn" onclick="ttsPlayPause()" title="Play / Pause">&#x25B6;</button>
            <button class="tts-btn" onclick="ttsStop()" title="Stop">&#x23F9;</button>
            <div class="tts-progress-wrap" onclick="ttsSeek(event)">
                <div class="tts-progress-fill" id="tts-progress-fill"></div>
            </div>
            <span class="tts-time" id="tts-time">0:00 / 0:00</span>
            <span class="tts-status" id="tts-status">Ready</span>
        </div>
        <details class="tts-text-details" id="tts-text-details">
            <summary>&#x1F4D6; Reading Text &#x2014; click to expand</summary>
            <div class="tts-text-container" id="tts-text-container">
                %%SENTENCES%%
            </div>
        </details>
        <audio id="tts-audio" preload="auto">
            <source src="data:audio/wav;base64,%%AUDIO%%" type="audio/wav">
        </audio>
        <script>
            const audio = document.getElementById('tts-audio');
            const playBtn = document.getElementById('tts-play-btn');
            const progressFill = document.getElementById('tts-progress-fill');
            const timeDisplay = document.getElementById('tts-time');
            const statusDisplay = document.getElementById('tts-status');
            const textDetails = document.getElementById('tts-text-details');
            const sentences = document.querySelectorAll('.tts-sentence');

            const sentLengths = [];
            let totalLen = 0;
            sentences.forEach(s => { const l = s.textContent.trim().length; sentLengths.push(l); totalLen += l; });
            const thresholds = [];
            let cumLen = 0;
            sentLengths.forEach(l => { cumLen += l; thresholds.push(cumLen / totalLen); });

            function getCurrentIdx(progress) {
                for (let i = 0; i < thresholds.length; i++) { if (progress < thresholds[i]) return i; }
                return thresholds.length - 1;
            }

            function fmtTime(sec) {
                const m = Math.floor(sec / 60);
                const s = Math.floor(sec % 60);
                return m + ':' + (s < 10 ? '0' : '') + s;
            }

            function updateHighlight() {
                if (!audio.duration || sentences.length === 0) return;
                const progress = audio.currentTime / audio.duration;
                const idx = getCurrentIdx(progress);
                sentences.forEach((s, i) => {
                    s.classList.remove('active');
                    if (i < idx) { s.classList.add('spoken'); } else { s.classList.remove('spoken'); }
                });
                if (idx < sentences.length) {
                    sentences[idx].classList.add('active');
                    sentences[idx].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            }

            audio.addEventListener('timeupdate', () => {
                const pct = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
                progressFill.style.width = pct + '%';
                timeDisplay.textContent = fmtTime(audio.currentTime) + ' / ' + fmtTime(audio.duration || 0);
                updateHighlight();
            });
            audio.addEventListener('play', () => { playBtn.textContent = '\u23F8'; statusDisplay.textContent = 'Playing'; textDetails.open = true; });
            audio.addEventListener('pause', () => { playBtn.textContent = '\u25B6'; if (audio.currentTime > 0 && audio.currentTime < audio.duration) statusDisplay.textContent = 'Paused'; });
            audio.addEventListener('ended', () => { playBtn.textContent = '\u25B6'; statusDisplay.textContent = 'Finished'; sentences.forEach(s => { s.classList.remove('active'); s.classList.add('spoken'); }); });

            function ttsPlayPause() { if (audio.paused) audio.play(); else audio.pause(); }
            function ttsStop() {
                audio.pause(); audio.currentTime = 0;
                playBtn.textContent = '\u25B6'; statusDisplay.textContent = 'Stopped';
                progressFill.style.width = '0%';
                timeDisplay.textContent = '0:00 / ' + fmtTime(audio.duration || 0);
                sentences.forEach(s => { s.classList.remove('active', 'spoken'); });
            }
            function ttsRestart() {
                audio.currentTime = 0;
                sentences.forEach(s => { s.classList.remove('active', 'spoken'); });
                audio.play();
            }
            function ttsSeek(event) {
                if (!audio.duration) return;
                const rect = event.currentTarget.getBoundingClientRect();
                const pct = (event.clientX - rect.left) / rect.width;
                audio.currentTime = pct * audio.duration;
            }
        </script>
    </body>
    </html>
    """.replace("%%SENTENCES%%", sentence_spans).replace("%%AUDIO%%", audio_b64)

    text_lines = max(3, min(12, len(sentences) // 2 + 2))
    height = 80 + text_lines * 28 + 50
    height = min(height, 500)
    components.html(player_html, height=height, scrolling=True)


# ============================================================================
# TELEMETRY SETUP
# ============================================================================
def setup_telemetry():
    """Initialize telemetry for logging conversations to Foundry."""
    if st.session_state.get("telemetry_initialized", False):
        return True
    try:
        project_client = AIProjectClient(
            endpoint=myEndpoint,
            credential=DefaultAzureCredential(),
        )
        conn_string = project_client.telemetry.get_application_insights_connection_string()
        configure_azure_monitor(
            connection_string=conn_string,
            enable_live_metrics=True,
            resource=create_resource(),
            enable_performance_counters=False,
        )
        enable_instrumentation(enable_sensitive_data=True)
        st.session_state["telemetry_initialized"] = True
        logger.info("Telemetry initialized successfully for ArchitectureIQ")
        return True
    except Exception as e:
        logger.warning(f"Could not initialize telemetry: {e}")
        return False


# ============================================================================
# LIVE TIMER — ticks every 0.5s so users always see progress
# ============================================================================
class _LiveTimer:
    """Background thread that continuously updates a Streamlit placeholder with elapsed time."""

    def __init__(self, placeholder, interval: float = 0.5):
        self._placeholder = placeholder
        self._interval = interval
        self._message = "Processing…"
        self._start = _time.time()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        # Attach Streamlit script-run context so writes reach the client
        try:
            from streamlit.runtime.scriptrunner import add_script_run_ctx
            add_script_run_ctx(self._thread)
        except Exception:
            pass  # older Streamlit — updates may queue until next event

    # -- public API ----------------------------------------------------------
    def start(self):
        self._thread.start()

    def update(self, msg: str):
        self._message = msg

    def stop(self, final_msg: str | None = None):
        self._stop_event.set()
        self._thread.join(timeout=2)
        if final_msg:
            self._placeholder.info(final_msg)

    # -- internal ------------------------------------------------------------
    def _tick(self):
        while not self._stop_event.is_set():
            elapsed = _time.time() - self._start
            try:
                self._placeholder.info(f"{self._message}  ⏱️ {elapsed:.1f}s")
            except Exception:
                break
            self._stop_event.wait(self._interval)


# ============================================================================
# AGENT ORCHESTRATION  (original MagenticBuilder logic with streaming UI)
# ============================================================================
async def run_architecture_workflow(task: str, ui_hooks: dict = None) -> dict:
    """
    Run the multi-agent Magentic workflow and return structured results.
    If ui_hooks is provided, streams output to Streamlit placeholders live.
    ui_hooks keys: summary_ph, agent_container, debug_ph, status_container
    """
    result: dict = {
        "summary": "",
        "agent_outputs": [],
        "debug_logs": [],
    }

    def _update_summary():
        """Show a waiting note while agents work; final summary is set after completion."""
        if ui_hooks and ui_hooks.get("summary_ph"):
            agent_count = len([ab for ab in result["agent_outputs"] if not ab.get("_streaming")])
            if agent_count:
                ui_hooks["summary_ph"].caption(
                    f"⏳ {agent_count} agent(s) have responded so far — see individual outputs on the right →"
                )
            else:
                ui_hooks["summary_ph"].caption("⏳ Waiting for agents to respond… see progress on the right →")

    def _show_final_summary():
        """Render the final composed summary into the left placeholder."""
        if ui_hooks and ui_hooks.get("summary_ph"):
            ui_hooks["summary_ph"].markdown(result["summary"])

    def _update_agents():
        if ui_hooks and ui_hooks.get("agent_container"):
            ui_hooks["agent_container"].empty()
            with ui_hooks["agent_container"].container():
                for i, ab in enumerate(result["agent_outputs"]):
                    is_last = (i == len(result["agent_outputs"]) - 1)
                    icon = "🟡" if is_last and ab.get("_streaming") else "🟢"
                    with st.expander(f"{icon} {ab['agent']}", expanded=is_last):
                        st.markdown(ab["text"])

    def _update_debug():
        if ui_hooks and ui_hooks.get("debug_ph"):
            ui_hooks["debug_ph"].text("\n".join(result["debug_logs"][-20:]))

    # -- live timer (continuous clock) ------------------------------------
    _timer: _LiveTimer | None = None
    if ui_hooks and ui_hooks.get("status_container"):
        _timer = _LiveTimer(ui_hooks["status_container"])
        _timer.start()

    def _update_status(msg: str):
        if _timer:
            _timer.update(msg)

    _workflow_start_time = _time.time()

    _update_status("Connecting to Azure AI Foundry…")

    client = AzureOpenAIResponsesClient(
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
        deployment_name=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    _update_status("Loading agents from Foundry…")

    provider = AzureAIProjectAgentProvider(
        credential=DefaultAzureCredential(),
        project_endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    )
    ideaagent = await provider.get_agent(name="ideaagent")
    business_owner_agent = await provider.get_agent(name="BusinessOwnerAgent")
    business_architect_agent = await provider.get_agent(name="BusinessArchitectAgent")
    solution_architect_agent = await provider.get_agent(name="SolutionArchitectAgent")
    raia_agent = await provider.get_agent(name="RAIAgent")
    architecture_summarizer_agent = await provider.get_agent(name="ArchitectureSummarizerAgent")

    manager_agent = Agent(
        name="MagenticManager",
        description="Orchestrator that coordinates the idea agent, business owner agent, business architect agent, solution architect agent, RAIAgent, and architecture summarizer agent to complete the task efficiently.",
        instructions="""You coordinate a team to complete complex tasks efficiently.
        - You have access to the following agents: ideaagent, business owner agent, business architect agent, solution architect agent, RAIAgent.
        - Pick the right agent(s) for each step of the task, and coordinate handoffs between agents.
        - At the end use the architecture summarizer agent to summarize the final architecture and reasoning in a clear and concise manner.
        You are a routing manager.
        You must invoke each participant exactly once, in the given order.
        Do not re-invoke any agent.
        Do not request revisions or follow-ups.
        Terminate immediately after the final agent completes.
        """,
        client=client,
    )

    _update_status("Building Magentic workflow…")

    workflow = MagenticBuilder(
        participants=[
            ideaagent, business_owner_agent, business_architect_agent,
            solution_architect_agent, raia_agent, architecture_summarizer_agent,
        ],
        intermediate_outputs=True,
        manager_agent=manager_agent,
        max_round_count=6,
        max_stall_count=0,
        max_reset_count=6,
    ).build()

    _update_status("Agents are collaborating…")

    last_response_id: str | None = None
    output_event: WorkflowEvent | None = None
    current_agent_text = ""
    current_agent_name = ""

    try:
        async for event in workflow.run(task, stream=True):
            if event.type == "output" and isinstance(event.data, AgentResponseUpdate):
                response_id = event.data.response_id
                if response_id != last_response_id:
                    # Flush previous agent block (mark done)
                    if current_agent_name and current_agent_text.strip():
                        # Remove _streaming flag from the last block
                        for ab in result["agent_outputs"]:
                            ab.pop("_streaming", None)
                        result["agent_outputs"].append({
                            "agent": current_agent_name,
                            "text": current_agent_text.strip(),
                        })
                    current_agent_name = event.executor_id or "Agent"
                    current_agent_text = ""
                    last_response_id = response_id
                    _update_status(f"Agent '{current_agent_name}' is responding…")
                    result["debug_logs"].append(f"Agent '{current_agent_name}' started streaming")
                    _update_debug()

                current_agent_text += str(event.data)

                # Live-update: append/overwrite current streaming agent block
                existing = [ab for ab in result["agent_outputs"] if ab.get("_streaming")]
                if existing:
                    existing[0]["text"] = current_agent_text
                else:
                    result["agent_outputs"].append({
                        "agent": current_agent_name,
                        "text": current_agent_text,
                        "_streaming": True,
                    })
                _update_agents()
                _update_summary()

            elif event.type == "magentic_orchestrator":
                evt_name = event.data.event_type.name
                if isinstance(event.data.content, Message):
                    result["debug_logs"].append(f"[Orchestrator {evt_name}] {event.data.content.text[:200]}")
                elif isinstance(event.data.content, MagenticProgressLedger):
                    result["debug_logs"].append(
                        f"[Orchestrator {evt_name}] Progress:\n{json.dumps(event.data.content.to_dict(), indent=2)}"
                    )
                else:
                    result["debug_logs"].append(f"[Orchestrator {evt_name}] {type(event.data.content).__name__}")
                _update_debug()

            elif event.type == "group_chat" and isinstance(event.data, GroupChatRequestSentEvent):
                result["debug_logs"].append(
                    f"[Round {event.data.round_index}] Request sent to: {event.data.participant_name}"
                )
                _update_status(f"Round {event.data.round_index} → {event.data.participant_name}")
                _update_debug()

            elif event.type == "output":
                output_event = event

    except Exception as exc:
        elapsed_total = _time.time() - _workflow_start_time
        tb_str = traceback.format_exc()
        err_msg = f"{type(exc).__name__}: {exc}"
        result["error"] = f"{err_msg}\n\n```\n{tb_str}```"
        result["debug_logs"].append(f"[ERROR @ {elapsed_total:.1f}s] {err_msg}")
        _update_debug()
        if _timer:
            _timer.stop(f"❌ Error after {elapsed_total:.1f}s — {type(exc).__name__}")
        result["elapsed_seconds"] = round(elapsed_total, 2)
        return result

    # Flush last streaming agent block and mark all done
    for ab in result["agent_outputs"]:
        ab.pop("_streaming", None)
    if current_agent_name and current_agent_text.strip():
        # Replace the streaming placeholder with the final text
        found = False
        for ab in result["agent_outputs"]:
            if ab["agent"] == current_agent_name:
                ab["text"] = current_agent_text.strip()
                found = True
                break
        if not found:
            result["agent_outputs"].append({
                "agent": current_agent_name,
                "text": current_agent_text.strip(),
            })

    # Build final summary from the output event (list of Messages)
    if output_event:
        result["summary"] = ""  # Replace streamed text with final formatted version
        outputs = cast(list[Message], output_event.data)
        for message in outputs:
            author = message.author_name or message.role
            result["summary"] += f"**{author}:**\n{message.text}\n\n"

    _show_final_summary()
    _update_agents()
    elapsed_total = _time.time() - _workflow_start_time
    if _timer:
        _timer.stop(f"✅ Complete — {elapsed_total:.1f}s total")

    result["elapsed_seconds"] = round(elapsed_total, 2)
    return result


def analyze_with_agent(task: str, ui_hooks: dict = None) -> dict:
    """Synchronous wrapper around the async workflow, with telemetry span."""
    with get_tracer().start_as_current_span("ArchitectureIQ-Analysis", kind=SpanKind.CLIENT) as span:
        trace_id = format_trace_id(span.get_span_context().trace_id)
        result = asyncio.run(run_architecture_workflow(task, ui_hooks=ui_hooks))
        result["trace_id"] = trace_id
    return result


# ============================================================================
# STREAMLIT UI
# ============================================================================
def main():
    st.set_page_config(
        page_title="ArchitectureIQ",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(MD3_CSS, unsafe_allow_html=True)

    # ── Top App Bar ──
    st.markdown("""
    <div class="md3-top-bar">
        <h1>🏗️ ArchitectureIQ</h1>
        <p>Multi-Agent Architecture Advisory — Powered by Microsoft Foundry &amp; Magentic Orchestration</p>
    </div>
    """, unsafe_allow_html=True)

    # ── Session state defaults ──
    for key, default in {
        "messages": [],
        "agent_outputs": [],
        "debug_logs": [],
        "error_log": None,
        "total_queries": 0,
        "telemetry_initialized": False,
        "tts_audio_bytes": None,
        "tts_clean_text": None,
        "tts_voice": "alloy",
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

    # ── Telemetry ──
    telemetry_ok = setup_telemetry()

    # ── Two-column layout with medium gap ──
    col_left, col_right = st.columns([1, 1], gap="medium")

    # ════════════════════════════════════════════════════════════════════════
    # LEFT — Summarized output & chat history
    # ════════════════════════════════════════════════════════════════════════
    with col_left:
        st.markdown('<div class="md3-label">💬 CONVERSATION &amp; SUMMARY</div>', unsafe_allow_html=True)

        chat_container = st.container(height=500, border=True)
        with chat_container:
            if not st.session_state.messages:
                st.markdown("""
                <div class="empty-state">
                    <div class="icon">🏗️</div>
                    <h3>Welcome to ArchitectureIQ</h3>
                    <p>Type a question below to start a multi-agent architecture analysis.</p>
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

            # Streaming placeholder for live summary (used during processing)
            summary_stream_ph = st.empty()

        # Stats & telemetry
        st.markdown(
            f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px;">'
            f'<span class="md3-chip">🔄 Queries: {st.session_state.total_queries}</span>'
            f'<span class="md3-chip">{"📊 Telemetry OK" if telemetry_ok else "⚠️ Telemetry off"}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Status line placeholder
        status_ph = st.empty()

        # ── Text-to-Speech controls ──
        last_assistant = None
        for msg in reversed(st.session_state.messages):
            if msg["role"] == "assistant":
                last_assistant = msg["content"]
                break

        if last_assistant:
            with st.expander("🔊 Read Aloud (Text-to-Speech)", expanded=False):
                voice_col, btn_col = st.columns([3, 1])
                with voice_col:
                    selected_voice = st.selectbox(
                        "Voice style",
                        options=list(TTS_VOICES.keys()),
                        format_func=lambda v: TTS_VOICES[v],
                        index=list(TTS_VOICES.keys()).index(st.session_state.tts_voice),
                        key="voice_selector",
                    )
                    st.session_state.tts_voice = selected_voice
                with btn_col:
                    st.markdown("<br>", unsafe_allow_html=True)
                    speak_clicked = st.button("🗣️ Speak", use_container_width=True)

                if speak_clicked:
                    with st.spinner("Generating speech…"):
                        audio_bytes, clean_text = generate_speech(last_assistant, voice=selected_voice)
                        st.session_state.tts_audio_bytes = audio_bytes
                        st.session_state.tts_clean_text = clean_text

                if st.session_state.tts_audio_bytes:
                    render_tts_player(st.session_state.tts_audio_bytes, st.session_state.tts_clean_text)

    # ════════════════════════════════════════════════════════════════════════
    # RIGHT — Individual agent outputs (expanders) + debug logs
    # ════════════════════════════════════════════════════════════════════════
    with col_right:
        st.markdown('<div class="md3-label">🤖 INDIVIDUAL AGENT OUTPUTS</div>', unsafe_allow_html=True)

        agent_outer = st.container(height=500, border=True)
        with agent_outer:
            if not st.session_state.agent_outputs:
                st.caption("Each agent's output will appear here after your first query.")
            else:
                for i, agent_block in enumerate(st.session_state.agent_outputs):
                    with st.expander(
                        f"🟢 {agent_block['agent']}",
                        expanded=(i == len(st.session_state.agent_outputs) - 1),
                    ):
                        st.markdown(agent_block["text"])

            # Live-streaming placeholder (re-rendered on each event)
            agent_stream_ph = st.empty()

            st.divider()

            # ── Error log (shown when an error occurred) ──
            if st.session_state.error_log:
                with st.expander("🚨 Error Details", expanded=True):
                    st.error("The workflow encountered an error. See details below.")
                    st.markdown(st.session_state.error_log)

            # ── Debug / orchestrator logs ──
            with st.expander("🐛 Debug & Orchestrator Logs", expanded=False):
                debug_stream_ph = st.empty()
                if not st.session_state.debug_logs:
                    debug_stream_ph.caption("Orchestrator events and debug info will appear here.")
                else:
                    debug_stream_ph.text("\n".join(st.session_state.debug_logs[-20:]))

    # ════════════════════════════════════════════════════════════════════════
    # Chat Input
    # ════════════════════════════════════════════════════════════════════════
    user_input = st.chat_input("Ask ArchitectureIQ anything…")

    if user_input:
        now = datetime.now().strftime("%I:%M %p")
        st.session_state.messages.append({"role": "user", "content": user_input, "timestamp": now})

        # Prepare streaming hooks – pass placeholders so the async loop can update them live
        ui_hooks = {
            "summary_ph": summary_stream_ph,
            "agent_container": agent_stream_ph,
            "debug_ph": debug_stream_ph,
            "status_container": status_ph,
        }

        result = analyze_with_agent(user_input, ui_hooks=ui_hooks)

        # Clear streaming placeholders (final data goes to session state)
        summary_stream_ph.empty()
        agent_stream_ph.empty()
        status_ph.empty()

        # Check if workflow returned an error
        if result.get("error"):
            st.session_state.error_log = result["error"]
            st.session_state.messages.append({
                "role": "assistant",
                "content": "⚠️ The workflow encountered an error. Check the **Error Details** panel on the right for more information.",
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
        st.session_state.debug_logs = result["debug_logs"]
        st.session_state.total_queries += 1
        st.session_state.tts_audio_bytes = None
        st.session_state.tts_clean_text = None

        st.rerun()


if __name__ == "__main__":
    main()