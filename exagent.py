# Before running the sample:
#   pip install --pre agent-framework agent-framework-foundry azure-ai-projects>=2.0.0b1
#   pip install azure-identity azure-monitor-opentelemetry python-dotenv
"""Connect to an existing Microsoft Foundry agent using the latest
``agent_framework_foundry.FoundryAgent`` class.

This replaces the previous hand-rolled ``AIProjectClient`` + raw
``openai_client.responses.create`` flow with the high-level
``FoundryAgent`` API, which transparently handles:
  * agent reference injection (no fragile ``agents.get`` round-trip)
  * MCP approval requests
  * tracing / Azure Monitor wiring
  * function-tool invocation
"""

from __future__ import annotations

import asyncio
import logging
import os

from dotenv import load_dotenv
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id

from agent_framework import observability
from agent_framework_foundry import FoundryAgent
from azure.identity.aio import DefaultAzureCredential

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT") or os.getenv("FOUNDRY_PROJECT_ENDPOINT")
AGENT_NAME = os.getenv("FOUNDRY_AGENT_NAME", "rfpagent")
AGENT_VERSION = os.getenv("FOUNDRY_AGENT_VERSION")  # optional; required for PromptAgents


def _print_response(response) -> None:
    """Pretty-print an AgentRunResponse including text and any citations."""
    print("FINAL RESPONSE:")
    print("=" * 80)

    text = getattr(response, "text", None)
    if text:
        print("\n📄 Response Text:\n")
        print(text)
        print()

    # Walk message contents to surface citations / tool calls if present.
    for message in getattr(response, "messages", []) or []:
        for content in getattr(message, "contents", []) or []:
            annotations = getattr(content, "annotations", None)
            if annotations:
                print("\n📚 Citations:")
                for i, annotation in enumerate(annotations, 1):
                    label = getattr(annotation, "text", None) or "Citation"
                    print(f"  [{i}] {label}")
                    file_citation = getattr(annotation, "file_citation", None)
                    if file_citation is not None:
                        src = getattr(file_citation, "file_name", "N/A")
                        print(f"      Source: {src}")
                        quote = getattr(file_citation, "quote", None)
                        if quote:
                            print(f"      Quote: {quote}")

            # Surface MCP / function tool calls when present.
            ctype = type(content).__name__
            if ctype.endswith("FunctionCallContent") or ctype.endswith("FunctionResultContent"):
                name = getattr(content, "name", None) or getattr(content, "function_name", "?")
                print(f"\n🔧 Tool {ctype}: {name}")

    print("\n" + "=" * 80)


async def existingagent() -> None:
    if not PROJECT_ENDPOINT:
        raise RuntimeError(
            "Set AZURE_AI_PROJECT (or FOUNDRY_PROJECT_ENDPOINT) to your Foundry project endpoint."
        )

    # FoundryAgent uses the async AIProjectClient under the hood, so use the
    # async DefaultAzureCredential and an async context manager.
    async with DefaultAzureCredential() as credential, FoundryAgent(
        project_endpoint=PROJECT_ENDPOINT,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        credential=credential,
        # The `agent_reference` extra_body field used by FoundryAgent is a
        # preview Responses API feature. Without preview opt-in the service
        # ignores the reference and returns 400 "Missing required parameter:
        # 'model'." because no model was sent (model lives on the agent).
        allow_preview=True,
    ) as agent:
        # Wire up Application Insights / OpenTelemetry via the project's
        # configured Application Insights resource. Safely no-ops with a
        # warning if App Insights isn't attached to the project.
        try:
            await agent.configure_azure_monitor(enable_sensitive_data=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Azure Monitor configuration skipped: %s", exc)

        print("Observability is set up. Starting Foundry agent run...")

        with observability.get_tracer().start_as_current_span(
            "existingrfpagent", kind=SpanKind.CLIENT
        ) as current_span:
            print(f"Trace ID: {format_trace_id(current_span.get_span_context().trace_id)}")
            print(
                f"Using Foundry agent: {AGENT_NAME}"
                + (f" (version {AGENT_VERSION})" if AGENT_VERSION else "")
            )

            response = await agent.run(
                "Summarize the RFP for virginia Railway Express project?"
            )

            _print_response(response)

    print("End of conversation with agent.")


if __name__ == "__main__":
    asyncio.run(existingagent())
