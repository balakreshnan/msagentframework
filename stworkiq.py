import logging
import re
import base64
import html as html_lib
from openai import AzureOpenAI
import streamlit as st
import streamlit.components.v1 as components
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.ai.projects import AIProjectClient
from agent_framework.observability import create_resource, enable_instrumentation, get_tracer
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
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
MD3_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
#MainMenu, footer, header {visibility: hidden;}
.stDeployButton {display: none;}

:root {
    --md-primary: #0D47A1;
    --md-on-primary: #FFFFFF;
    --md-primary-container: #BBDEFB;
    --md-surface: #FAFBFE;
    --md-surface-container: #FFFFFF;
    --md-surface-high: #E3F2FD;
    --md-on-surface: #1C1B1F;
    --md-on-surface-var: #49454F;
    --md-outline: #90CAF9;
    --md-outline-var: #E3F2FD;
    --md-secondary: #1565C0;
    --md-tertiary: #1976D2;
    --md-error: #B3261E;
    --md-success: #2E7D32;
    --md-warning: #F57C00;
    --md-shadow: rgba(0,0,0,0.08);
}

/* ── Top Bar ── */
.md3-top-bar {
    background: linear-gradient(135deg, #0D47A1 0%, #1565C0 40%, #1976D2 100%);
    color: white; padding: 20px 32px;
    border-radius: 0 0 28px 28px;
    margin: -1rem -1rem 1.5rem -1rem;
    box-shadow: 0 4px 16px rgba(13,71,161,0.3);
}
.md3-top-bar h1 { margin:0; font-size:1.6rem; font-weight:600; letter-spacing:-0.02em; }
.md3-top-bar p  { margin:4px 0 0; font-size:0.85rem; opacity:0.85; font-weight:300; }

/* ── Cards ── */
.md3-card {
    background: var(--md-surface-container);
    border: 1px solid var(--md-outline);
    border-radius: 16px;
    box-shadow: 0 1px 3px var(--md-shadow), 0 4px 12px var(--md-shadow);
    transition: box-shadow 0.2s;
}
.md3-card:hover { box-shadow: 0 2px 6px var(--md-shadow), 0 8px 24px var(--md-shadow); }

/* ── Section labels ── */
.md3-label {
    font-size: 0.7rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: var(--md-secondary);
    margin-bottom: 8px; display: flex; align-items: center; gap: 6px;
}

/* ── Chat bubbles ── */
.chat-bubble-user {
    background: linear-gradient(135deg, #0D47A1, #1565C0);
    color: white; padding: 14px 20px;
    border-radius: 20px 20px 6px 20px;
    margin: 8px 0; max-width: 85%; margin-left: auto;
    font-size: 0.92rem; line-height: 1.55;
    box-shadow: 0 2px 8px rgba(13,71,161,0.25);
    word-wrap: break-word;
}
.chat-bubble-assistant {
    background: var(--md-surface-high);
    color: var(--md-on-surface); padding: 14px 20px;
    border-radius: 20px 20px 20px 6px;
    margin: 8px 0; max-width: 85%; font-size: 0.92rem; line-height: 1.55;
    border: 1px solid var(--md-outline); word-wrap: break-word;
}
.chat-timestamp {
    font-size: 0.65rem; color: var(--md-on-surface-var);
    margin-top: 2px; opacity: 0.7;
}

/* ── Chips ── */
.md3-chip {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--md-surface-high); border: 1px solid var(--md-outline);
    padding: 6px 14px; border-radius: 20px;
    font-size: 0.78rem; font-weight: 500; color: var(--md-on-surface);
}

/* ── Debug / workflow messages ── */
.debug-msg {
    background: #FFF8E1; border-left: 4px solid #FFA000;
    padding: 8px 12px; margin: 4px 0; border-radius: 0 8px 8px 0;
    font-family: 'Cascadia Code','Consolas',monospace; font-size: 0.75rem;
}
.workflow-step {
    background: #F3E5F5; border-left: 4px solid #7B1FA2;
    padding: 8px 12px; margin: 4px 0; border-radius: 0 8px 8px 0;
    font-size: 0.82rem;
}
.agent-output-card {
    background: #E3F2FD; border-left: 4px solid #1565C0;
    padding: 10px 14px; margin: 6px 0; border-radius: 0 12px 12px 0;
}

/* ── Empty state ── */
.empty-state {
    text-align: center; padding: 60px 20px; color: var(--md-on-surface-var);
}
.empty-state .icon { font-size: 3rem; margin-bottom: 12px; }
.empty-state h3 { margin: 0; font-weight: 500; color: var(--md-on-surface); }
.empty-state p  { font-size: 0.85rem; margin-top: 6px; }

/* ── Progress bar ── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #0D47A1, #42A5F5);
}
/* ── Divider ── */
.md3-divider {
    height: 1px; margin: 16px 0;
    background: linear-gradient(90deg, transparent, var(--md-outline-var), transparent);
}
/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: var(--md-surface-high); border-radius: 3px; }
::-webkit-scrollbar-thumb { background: var(--md-outline); border-radius: 3px; }

/* ── Streamlit overrides ── */
.stChatInput > div {
    border-radius: 28px !important;
    border: 2px solid var(--md-outline) !important;
    box-shadow: 0 2px 8px var(--md-shadow) !important;
}
.stChatInput > div:focus-within {
    border-color: var(--md-primary) !important;
    box-shadow: 0 2px 12px rgba(13,71,161,0.18) !important;
}
.stExpander {
    border: 1px solid var(--md-outline) !important;
    border-radius: 16px !important;
    box-shadow: 0 1px 4px var(--md-shadow) !important;
    margin-bottom: 8px !important;
}
</style>
"""


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
        logger.info("Telemetry initialized successfully for WorkIQ")
        return True
    except Exception as e:
        logger.warning(f"Could not initialize telemetry: {e}")
        return False


# ============================================================================
# ANALYZE WITH AGENT
# ============================================================================
def analyze_with_agent(query: str, image_bytes: bytes = None):
    """Analyze query using the WorkIQ agent with optional image support."""
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=myEndpoint, credential=credential)

    results = {
        "final_response": "",
        "workflow_steps": [],
        "individual_agent_outputs": [],
        "mcp_tool_calls": [],
        "debug_logs": [],
        "token_usage": {"input": 0, "output": 0, "total": 0},
    }

    with get_tracer().start_as_current_span("WorkIQ-Analysis", kind=SpanKind.CLIENT) as span:
        trace_id = format_trace_id(span.get_span_context().trace_id)
        results["trace_id"] = trace_id

        with project_client:
            workflow = {"name": "workiqagent", "version": "13"}

            openai_client = project_client.get_openai_client()
            conversation = openai_client.conversations.create()
            results["debug_logs"].append(f"Created conversation (id: {conversation.id})")

            # Build input – attach image when supplied
            input_content = query
            if image_bytes:
                image_b64 = base64.b64encode(image_bytes).decode("utf-8")
                input_content = f"{query}\n\n[Image attached for analysis]"
                results["debug_logs"].append(f"Image attached: {len(image_bytes)} bytes")

            stream = openai_client.responses.create(
                conversation=conversation.id,
                extra_body={
                    "agent_reference": {
                        "name": workflow["name"],
                        "type": "agent_reference",
                    }
                },
                input=input_content,
                stream=True,
                metadata={"x-ms-debug-mode-enabled": "1"},
            )

            current_text = ""
            current_agent_id = None
            current_agent_output = ""
            current_mcp_calls = {}

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
                    if current_agent_id and current_agent_output:
                        results["individual_agent_outputs"].append({
                            "agent_id": current_agent_id,
                            "output": current_agent_output,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        })
                    current_agent_id = getattr(event.item, "action_id", None) or "Agent"
                    current_agent_output = ""
                    results["workflow_steps"].append({
                        "action_id": current_agent_id,
                        "status": "started",
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    results["debug_logs"].append(f"Agent '{current_agent_id}' started")

                elif (
                    event.type == "response.output_item.done"
                    and hasattr(event, "item")
                    and getattr(event.item, "type", "") == "workflow_action"
                ):
                    if current_agent_output:
                        results["individual_agent_outputs"].append({
                            "agent_id": event.item.action_id,
                            "output": current_agent_output,
                            "status": event.item.status,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        })
                        current_agent_output = ""
                    results["workflow_steps"].append({
                        "action_id": event.item.action_id,
                        "status": event.item.status,
                        "previous_action": getattr(event.item, "previous_action_id", None),
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    results["debug_logs"].append(
                        f"Agent '{event.item.action_id}' completed ({event.item.status})"
                    )

                elif (
                    event.type == "response.output_item.added"
                    and hasattr(event, "item")
                    and getattr(event.item, "type", "") in ("mcp_call", "function_call")
                ):
                    tool_name = getattr(event.item, "name", "Unknown Tool")
                    server_label = getattr(event.item, "server_label", "")
                    output_index = getattr(event, "output_index", id(event))
                    current_mcp_calls[output_index] = {
                        "tool_name": tool_name,
                        "server_label": server_label,
                        "arguments": "",
                    }
                    label = f"{server_label}/{tool_name}" if server_label else tool_name
                    results["debug_logs"].append(f"MCP Tool '{label}' called")

                elif event.type in (
                    "response.mcp_call_arguments.delta",
                    "response.function_call_arguments.delta",
                ):
                    output_index = getattr(event, "output_index", None)
                    if output_index in current_mcp_calls:
                        current_mcp_calls[output_index]["arguments"] += getattr(event, "delta", "")

                elif (
                    event.type == "response.output_item.done"
                    and hasattr(event, "item")
                    and getattr(event.item, "type", "") in ("mcp_call", "function_call")
                ):
                    tool_name = getattr(event.item, "name", "Unknown Tool")
                    server_label = getattr(event.item, "server_label", "")
                    arguments = getattr(event.item, "arguments", "")
                    output = getattr(event.item, "output", "")
                    status = getattr(event.item, "status", "completed")
                    output_index = getattr(event, "output_index", None)
                    if not arguments and output_index in current_mcp_calls:
                        arguments = current_mcp_calls[output_index].get("arguments", "")
                    results["mcp_tool_calls"].append({
                        "tool_name": tool_name,
                        "server_label": server_label,
                        "arguments": arguments,
                        "output": output,
                        "status": status,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                    })
                    label = f"{server_label}/{tool_name}" if server_label else tool_name
                    results["debug_logs"].append(f"MCP Tool '{label}' completed ({status})")
                    if output_index in current_mcp_calls:
                        del current_mcp_calls[output_index]

                elif event.type == "response.output_text.delta":
                    current_text += event.delta
                    current_agent_output += event.delta

                elif event.type == "response.completed":
                    if hasattr(event, "response") and hasattr(event.response, "usage"):
                        u = event.response.usage
                        results["token_usage"] = {
                            "input": getattr(u, "input_tokens", 0) or 0,
                            "output": getattr(u, "output_tokens", 0) or 0,
                            "total": getattr(u, "total_tokens", 0) or 0,
                        }
                    results["debug_logs"].append("Response completed")

                else:
                    results["debug_logs"].append(f"Event: {event.type}")

            if current_text and not results["final_response"].strip():
                results["final_response"] = current_text

            results["debug_logs"].append("Conversation completed")
            openai_client.conversations.delete(conversation_id=conversation.id)

    return results


# ============================================================================
# TEXT-TO-SPEECH
# ============================================================================
def clean_text_for_tts(text: str) -> str:
    """Strip markdown and non-speech elements from text."""
    text = re.sub(r'⏱️.*$', '', text, flags=re.MULTILINE)
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


# Available TTS voices with descriptions
TTS_VOICES = {
    "alloy": "Alloy — Neutral, balanced",
    "echo": "Echo — Deeper, authoritative",
    "fable": "Fable — Expressive storytelling",
    "onyx": "Onyx — Deep, confident",
    "nova": "Nova — Bright, energetic",
    "shimmer": "Shimmer — Soft, calm",
}


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

    # Split into sentences for highlighting
    sentences = re.split(r'(?<=[.!?])\s+|\n+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text]

    # Build HTML-escaped sentence spans
    sentence_spans = ""
    for i, sent in enumerate(sentences):
        escaped = html_lib.escape(sent)
        sentence_spans += f'<span id="sent-{i}" class="tts-sentence">{escaped} </span>'

    # Build the HTML template without f-string to avoid brace conflicts with JS
    player_html = """
    <!DOCTYPE html>
    <html>
    <head>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; padding: 12px; background: transparent; }
        .tts-controls {
            display: flex; align-items: center; gap: 8px; padding: 10px 14px;
            background: linear-gradient(135deg, #E3F2FD, #BBDEFB); border-radius: 14px;
            margin-bottom: 12px; box-shadow: 0 2px 8px rgba(13,71,161,0.1);
        }
        .tts-btn {
            border: none; background: #0D47A1; color: white; width: 34px; height: 34px;
            border-radius: 50%; cursor: pointer; font-size: 14px; display: flex;
            align-items: center; justify-content: center; transition: all 0.2s;
            box-shadow: 0 2px 4px rgba(0,0,0,0.15);
        }
        .tts-btn:hover { background: #1565C0; transform: scale(1.1); }
        .tts-btn:active { transform: scale(0.95); }
        .tts-progress-wrap {
            flex: 1; height: 8px; background: rgba(255,255,255,0.7); border-radius: 4px;
            cursor: pointer; position: relative; overflow: hidden;
        }
        .tts-progress-fill {
            height: 100%; background: linear-gradient(90deg, #0D47A1, #42A5F5);
            border-radius: 4px; width: 0%; transition: width 0.15s linear;
        }
        .tts-time { font-size: 11px; color: #49454F; min-width: 75px; text-align: right; font-weight: 500; }
        .tts-status { font-size: 11px; color: #0D47A1; font-weight: 600; min-width: 60px; }
        .tts-text-details {
            margin-top: 10px; border: 1px solid #90CAF9; border-radius: 14px;
            overflow: hidden; background: #FAFBFE;
        }
        .tts-text-details summary {
            padding: 10px 16px; cursor: pointer; font-size: 12.5px; font-weight: 600;
            color: #0D47A1; background: #E3F2FD; user-select: none;
            list-style: none; display: flex; align-items: center; gap: 6px;
        }
        .tts-text-details summary::-webkit-details-marker { display: none; }
        .tts-text-details summary::before { content: '▶'; font-size: 10px; transition: transform 0.2s; }
        .tts-text-details[open] summary::before { transform: rotate(90deg); }
        .tts-text-container {
            padding: 14px 16px; line-height: 1.9; font-size: 13.5px; color: #1C1B1F;
            max-height: 300px; overflow-y: auto; scroll-behavior: smooth;
        }
        .tts-sentence { padding: 1px 2px; border-radius: 4px; transition: background-color 0.3s ease, color 0.3s ease; }
        .tts-sentence.active {
            background: linear-gradient(135deg, #BBDEFB, #90CAF9);
            padding: 2px 4px; border-radius: 6px; font-weight: 500;
        }
        .tts-sentence.spoken { color: #78909C; }
    </style>
    </head>
    <body>
        <div class="tts-controls">
            <button class="tts-btn" onclick="ttsRestart()" title="Restart from beginning">⏮</button>
            <button class="tts-btn" id="tts-play-btn" onclick="ttsPlayPause()" title="Play / Pause">▶</button>
            <button class="tts-btn" onclick="ttsStop()" title="Stop">⏹</button>
            <div class="tts-progress-wrap" onclick="ttsSeek(event)">
                <div class="tts-progress-fill" id="tts-progress-fill"></div>
            </div>
            <span class="tts-time" id="tts-time">0:00 / 0:00</span>
            <span class="tts-status" id="tts-status">Ready</span>
        </div>
        <details class="tts-text-details" id="tts-text-details">
            <summary>📖 Reading Text — click to expand</summary>
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
            const textContainer = document.getElementById('tts-text-container');
            const textDetails = document.getElementById('tts-text-details');
            const sentences = document.querySelectorAll('.tts-sentence');

            // Compute cumulative thresholds based on character length
            const sentLengths = [];
            let totalLen = 0;
            sentences.forEach(s => {
                const len = s.textContent.trim().length;
                sentLengths.push(len);
                totalLen += len;
            });
            const thresholds = [];
            let cumLen = 0;
            sentLengths.forEach(len => {
                cumLen += len;
                thresholds.push(cumLen / totalLen);
            });

            function getCurrentIdx(progress) {
                for (let i = 0; i < thresholds.length; i++) {
                    if (progress < thresholds[i]) return i;
                }
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
                    if (i < idx) { s.classList.add('spoken'); }
                    else { s.classList.remove('spoken'); }
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

            audio.addEventListener('play', () => {
                playBtn.textContent = '⏸';
                statusDisplay.textContent = 'Playing';
                textDetails.open = true;
            });

            audio.addEventListener('pause', () => {
                playBtn.textContent = '▶';
                if (audio.currentTime > 0 && audio.currentTime < audio.duration) {
                    statusDisplay.textContent = 'Paused';
                }
            });

            audio.addEventListener('ended', () => {
                playBtn.textContent = '▶';
                statusDisplay.textContent = 'Finished';
                sentences.forEach(s => { s.classList.remove('active'); s.classList.add('spoken'); });
            });

            function ttsPlayPause() {
                if (audio.paused) { audio.play(); }
                else { audio.pause(); }
            }

            function ttsStop() {
                audio.pause();
                audio.currentTime = 0;
                playBtn.textContent = '▶';
                statusDisplay.textContent = 'Stopped';
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
# SESSION STATE
# ============================================================================
def init_session():
    """Initialize all session state variables."""
    defaults = {
        "messages": [],
        "agent_outputs": [],
        "debug_logs": [],
        "current_image_bytes": None,
        "processing": False,
        "telemetry_initialized": False,
        "conversation_count": 0,
        "last_elapsed": None,
        "tts_audio_bytes": None,
        "tts_clean_text": None,
        "tts_voice": "alloy",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ============================================================================
# HELPERS
# ============================================================================
def _add_debug(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    st.session_state.debug_logs.append({"timestamp": ts, "level": level, "message": msg})
    logger.info(f"[{level}] {msg}")


def _add_message(role: str, content: str, image: bytes = None):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.messages.append({"role": role, "content": content, "timestamp": ts, "image": image})


def _add_agent_output(kind: str, content, trace_id: str = None):
    ts = datetime.now().strftime("%H:%M:%S")
    st.session_state.agent_outputs.append({"type": kind, "content": content, "timestamp": ts, "trace_id": trace_id})


# ============================================================================
# MAIN UI
# ============================================================================
def main():
    st.set_page_config(
        page_title="WorkIQ",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(MD3_CSS, unsafe_allow_html=True)
    init_session()
    telemetry_ok = setup_telemetry()

    # ── Top App Bar ──
    st.markdown("""
    <div class="md3-top-bar">
        <h1>🧠 WorkIQ</h1>
        <p>Your Intelligent Work Advisor — Powered by Microsoft Foundry Agents</p>
    </div>
    """, unsafe_allow_html=True)

    # Telemetry indicator
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if telemetry_ok:
            st.success("📊 Telemetry connected to Azure Foundry")
        else:
            st.warning("⚠️ Telemetry not connected")

    st.markdown('<div class="md3-divider"></div>', unsafe_allow_html=True)

    # ── Two-column layout ──
    col_chat, col_output = st.columns([1, 1], gap="medium")

    # ================================================================
    # LEFT COLUMN — Chat & Image Upload
    # ================================================================
    with col_chat:
        st.markdown('<div class="md3-label">💬 Chat &amp; Upload</div>', unsafe_allow_html=True)

        # Image upload
        with st.expander("📤 Upload an Image", expanded=False):
            uploaded = st.file_uploader(
                "Choose an image to include with your question",
                type=["png", "jpg", "jpeg", "gif", "webp", "bmp"],
                help="Upload an image for WorkIQ to analyse alongside your question.",
            )
            if uploaded is not None:
                img_bytes = uploaded.read()
                st.session_state.current_image_bytes = img_bytes
                st.image(img_bytes, caption="Preview", use_container_width=True)
                st.markdown(
                    f'<span class="md3-chip">📁 {uploaded.name}</span> '
                    f'<span class="md3-chip">📐 {len(img_bytes)/1024:.1f} KB</span>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="md3-divider"></div>', unsafe_allow_html=True)
        st.markdown('<div class="md3-label">📜 Conversation History</div>', unsafe_allow_html=True)

        chat_container = st.container(height=500)
        with chat_container:
            if not st.session_state.messages:
                st.markdown("""
                <div class="empty-state">
                    <div class="icon">🧠</div>
                    <h3>Welcome to WorkIQ</h3>
                    <p>Upload an image or type a question below to get started.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                for msg in st.session_state.messages:
                    if msg["role"] == "user":
                        st.markdown(f"""
                        <div class="chat-bubble-user">
                            {msg["content"]}
                            <div class="chat-timestamp">🕐 {msg["timestamp"]}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        if msg.get("image"):
                            st.image(msg["image"], caption="📎 Attached Image", use_container_width=True)
                    else:
                        st.markdown(f"""
                        <div class="chat-bubble-assistant">
                            {msg["content"]}
                            <div class="chat-timestamp">🕐 {msg["timestamp"]}</div>
                        </div>
                        """, unsafe_allow_html=True)

    # ================================================================
    # RIGHT COLUMN — Agent Output & Debug
    # ================================================================
    with col_output:
        st.markdown('<div class="md3-label">🤖 Agent Output</div>', unsafe_allow_html=True)
        show_debug = st.toggle("🔧 Show Debug Logs", value=False)

        output_container = st.container(height=500)
        with output_container:
            # Debug logs
            if show_debug and st.session_state.debug_logs:
                st.markdown("#### 🔧 Debug Logs")
                level_colors = {"INFO": "#1565C0", "SUCCESS": "#2E7D32", "ERROR": "#B3261E", "WARNING": "#F57C00"}
                for entry in st.session_state.debug_logs[-20:]:
                    clr = level_colors.get(entry["level"], "#72787E")
                    st.markdown(
                        f'<div class="debug-msg">'
                        f'<span style="color:{clr};font-weight:bold;">[{entry["level"]}]</span> '
                        f'<span style="opacity:0.7;font-size:0.7rem;">{entry["timestamp"]}</span><br>'
                        f'{entry["message"]}</div>',
                        unsafe_allow_html=True,
                    )
                st.markdown("---")

            # Agent outputs
            if not st.session_state.agent_outputs:
                st.markdown("""
                <div class="empty-state">
                    <div class="icon">⚙️</div>
                    <h3>No Analysis Yet</h3>
                    <p>Agent responses and workflow steps will appear here.</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                # Latest result
                result_outputs = [o for o in st.session_state.agent_outputs if o["type"] == "result"]
                if result_outputs:
                    latest = result_outputs[-1]
                    content = latest["content"]
                    trace_id = latest.get("trace_id", "")

                    if trace_id:
                        st.markdown(
                            f'<div class="md3-chip">🔗 Trace: {trace_id[:16]}…</div> '
                            f'<span style="font-size:0.7rem;color:#49454F;">{latest["timestamp"]}</span>',
                            unsafe_allow_html=True,
                        )

                    # Individual agent outputs
                    if isinstance(content, dict) and content.get("individual_agent_outputs"):
                        st.markdown("##### 🔍 Individual Agent Outputs")
                        for idx, ao in enumerate(content["individual_agent_outputs"]):
                            agent_id = ao.get("agent_id", f"Agent {idx+1}")
                            agent_text = ao.get("output", "No output")
                            agent_time = ao.get("timestamp", "")
                            status = ao.get("status", "completed")
                            icon = "✅" if status == "completed" else "🔄"
                            with st.expander(f"{icon} {agent_id} @ {agent_time}", expanded=False):
                                st.markdown(agent_text)

                    st.markdown('<div class="md3-divider"></div>', unsafe_allow_html=True)

                    # MCP Tool Calls
                    if isinstance(content, dict) and content.get("mcp_tool_calls"):
                        st.markdown("##### 🔧 MCP Tool Calls")
                        for idx, tc in enumerate(content["mcp_tool_calls"]):
                            tool_name = tc.get("tool_name", f"Tool {idx+1}")
                            server_label = tc.get("server_label", "")
                            status = tc.get("status", "completed")
                            tc_time = tc.get("timestamp", "")
                            icon = "✅" if status == "completed" else "🔄"
                            label = f"{server_label}/{tool_name}" if server_label else tool_name
                            with st.expander(f"{icon} {label} @ {tc_time}", expanded=False):
                                if tc.get("arguments"):
                                    st.markdown("**Input:**")
                                    st.code(tc["arguments"], language="json")
                                if tc.get("output"):
                                    st.markdown("**Output:**")
                                    st.markdown(tc["output"])
                                if not tc.get("arguments") and not tc.get("output"):
                                    st.caption("No input/output captured")
                        st.markdown('<div class="md3-divider"></div>', unsafe_allow_html=True)

                    # Workflow steps
                    if isinstance(content, dict) and content.get("workflow_steps"):
                        with st.expander("📋 Workflow Steps", expanded=False):
                            for step in content["workflow_steps"]:
                                icon = "✅" if step.get("status") == "completed" else "🔄"
                                st.markdown(
                                    f"{icon} **{step.get('action_id')}** – "
                                    f"{step.get('status')} @ {step.get('timestamp')}"
                                )

                    # Token usage
                    if isinstance(content, dict) and content.get("token_usage"):
                        tu = content["token_usage"]
                        st.markdown(
                            f'<span class="md3-chip">⬆ {tu.get("input",0)}</span> '
                            f'<span class="md3-chip">⬇ {tu.get("output",0)}</span> '
                            f'<span class="md3-chip">Σ {tu.get("total",0)}</span>',
                            unsafe_allow_html=True,
                        )

                    # Final response (in nice readable form)
                    if isinstance(content, dict) and content.get("final_response"):
                        st.markdown("---")
                        st.markdown(content["final_response"])

        # ── Text-to-Speech Section ──
        if st.session_state.messages and any(m["role"] == "assistant" for m in st.session_state.messages):
            st.markdown('<div class="md3-divider"></div>', unsafe_allow_html=True)
            st.markdown('<div class="md3-label">🔊 Text-to-Speech</div>', unsafe_allow_html=True)

            last_assistant_msg = None
            for msg in reversed(st.session_state.messages):
                if msg["role"] == "assistant":
                    last_assistant_msg = msg["content"]
                    break

            if last_assistant_msg:
                voice_col, btn_col1, btn_col2 = st.columns([1, 1, 1])
                with voice_col:
                    voice_options = list(TTS_VOICES.keys())
                    voice_labels = list(TTS_VOICES.values())
                    current_idx = voice_options.index(st.session_state.get("tts_voice", "alloy"))
                    selected_label = st.selectbox(
                        "Voice",
                        voice_labels,
                        index=current_idx,
                        label_visibility="collapsed",
                    )
                    st.session_state.tts_voice = voice_options[voice_labels.index(selected_label)]
                with btn_col1:
                    if st.button("🔊 Listen to Response", use_container_width=True):
                        with st.spinner("Generating speech…"):
                            try:
                                audio_bytes, clean_text = generate_speech(
                                    last_assistant_msg, voice=st.session_state.tts_voice
                                )
                                st.session_state.tts_audio_bytes = audio_bytes
                                st.session_state.tts_clean_text = clean_text
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed to generate speech: {e}")
                with btn_col2:
                    if st.session_state.get("tts_audio_bytes") and st.button("🗑️ Clear Audio", use_container_width=True):
                        st.session_state.tts_audio_bytes = None
                        st.session_state.tts_clean_text = None
                        st.rerun()

                if st.session_state.get("tts_audio_bytes"):
                    render_tts_player(st.session_state.tts_audio_bytes, st.session_state.tts_clean_text)

    # ================================================================
    # CHAT INPUT (full-width, bottom)
    # ================================================================
    st.markdown('<div class="md3-divider"></div>', unsafe_allow_html=True)
    user_input = st.chat_input(
        placeholder="Ask WorkIQ anything — type your question here…",
        disabled=st.session_state.processing,
    )

    if user_input:
        st.session_state.tts_audio_bytes = None
        st.session_state.tts_clean_text = None
        image_bytes = st.session_state.current_image_bytes
        _add_message("user", user_input, image_bytes)
        _add_debug(f"User query: {user_input[:80]}…")
        if image_bytes:
            _add_debug(f"Image attached: {len(image_bytes)} bytes")

        st.session_state.processing = True
        st.session_state.conversation_count += 1

        with st.spinner("🔄 WorkIQ is analysing your request…", show_time=True):
            t_start = time.time()
            try:
                _add_debug("Calling WorkIQ agent…")
                results = analyze_with_agent(user_input, image_bytes)
                elapsed = round(time.time() - t_start, 2)
                st.session_state.last_elapsed = elapsed

                # Workflow steps → agent output panel
                for step in results.get("workflow_steps", []):
                    _add_agent_output("workflow", step)

                # Debug logs from agent
                for log in results.get("debug_logs", []):
                    _add_agent_output("debug", log)

                # Full result
                _add_agent_output("result", results, results.get("trace_id"))

                # Summary into chat with elapsed time
                summary = results.get("final_response", "Analysis complete.")
                summary += f"\n\n⏱️ *Processed in {elapsed}s*"
                _add_message("assistant", summary)
                _add_debug(f"Completed in {elapsed}s. Trace: {results.get('trace_id','N/A')}", "SUCCESS")

            except Exception as e:
                elapsed = round(time.time() - t_start, 2)
                st.session_state.last_elapsed = elapsed
                err = str(e)
                _add_debug(f"Error after {elapsed}s: {err}", "ERROR")
                _add_agent_output("error", err)
                _add_message("assistant", f"Sorry, an error occurred: {err}")
            finally:
                st.session_state.processing = False

        st.rerun()

    # ================================================================
    # SIDEBAR
    # ================================================================
    with st.sidebar:
        st.markdown("### ⚙️ WorkIQ Settings")
        st.markdown("---")

        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.messages = []
            st.session_state.agent_outputs = []
            st.session_state.debug_logs = []
            st.rerun()

        if st.button("🖼️ Clear Image", use_container_width=True):
            st.session_state.current_image_bytes = None
            st.rerun()

        st.markdown("---")
        st.markdown("### 📊 Session Statistics")
        st.metric("Conversations", st.session_state.conversation_count)
        st.metric("Messages", len(st.session_state.messages))
        st.metric("Agent Outputs", len(st.session_state.agent_outputs))
        if st.session_state.last_elapsed is not None:
            st.metric("Last Processing Time", f"{st.session_state.last_elapsed}s")

        st.markdown("---")
        st.markdown("### 🔗 Telemetry")
        if st.session_state.get("telemetry_initialized"):
            st.success("✅ Connected to Foundry")
        else:
            st.warning("⚠️ Not connected")

        st.markdown("---")
        st.markdown(
            '<div style="text-align:center;color:#72787E;font-size:11px;">'
            "WorkIQ v1.0<br>Powered by Azure AI Foundry</div>",
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()