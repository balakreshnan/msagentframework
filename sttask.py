import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from random import randint
from typing import Annotated, Dict, List, Any
from openai import AzureOpenAI
import requests
import streamlit as st
from utils import get_weather, fetch_stock_data

from agent_framework import ChatAgent, ChatMessage
from agent_framework import AgentProtocol, AgentThread, HostedMCPTool, HostedFileSearchTool, HostedVectorStoreContent
from agent_framework.azure import AzureAIAgentClient
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
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

async def multi_agent_interaction(query: str) -> str:
    returntxt = ""
    credentialdefault = DefaultAzureCredential()
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(async_credential=credentialdefault) as chat_client,
    ):
        
        taskplanner_agent = chat_client.create_agent(
            name="taskplanner",
            instructions="""You are an intelligent business process automation assistant. Your goal is to break down any user request into a clear, executable sequence of tasks using only the predefined task list below.

            ### Available Task List (in JSON format):
            {
            "Salesforce_CRM": [
                "CreateLead", "AssignLead", "QualifyLead", "ConvertLeadToOpportunity", "GetAccount", "CreateContact",
                "CreateOpportunity", "UpdateOpportunityStage", "LogCallActivity", "SendEmail", "AttachDocument",
                "RunSOQLReport", "CloseWonOpportunity", "GenerateForecast", "SyncCampaignData", "CreateCase",
                "UpdateCSATScore", "BulkDeleteLeads"
            ],
            "Order_Processing_SAP": [
                "CreateSalesOrder", "CheckInventory", "ApplyPricing", "ApproveOrder", "CreateDelivery", "PickPackItems",
                "CreateOutboundDelivery", "PostGoodsIssue", "GetOrderStatus", "ModifyOrderQuantity", "SyncWithCRM",
                "CreateInvoice", "ProcessReturn", "GetOrderHistory", "CancelOrder", "BatchProcessOrders",
                "AddSpecialInstructions", "LinkToProduction"
            ],
            "Manufacturing_Execution_Systems": [
                "StartProductionOrder", "AssignResources", "TrackMachineStatus", "RecordMaterialConsumption",
                "MonitorWIP", "ReportYieldQuality", "LogReworkScrap", "UpdateOrderInProgress", "SyncWithSAP",
                "GenerateShiftReport", "ScheduleMaintenance", "TrackOperatorPerformance", "CompleteProductionOrder",
                "QueryProductionHistory", "AlertAnomalies", "TraceBatch", "OptimizeSequence", "QualityControlInterface"
            ],
            "Finance_SAP": [
                "PostCustomerInvoice", "ProcessVendorPayment", "GetGLBalance", "CreateFixedAsset", "RunMonthEndClose",
                "GenerateFinancialReport", "BankReconciliation", "UpdateCostCenter", "SyncOrderInvoice", "CalculateTax",
                "BudgetVsActual", "ProcessPayroll", "CurrencyAdjustment", "PostJournalEntry", "AuditTrail",
                "CashFlowForecast", "FiscalYearClose", "IntercompanyTransaction"
            ],
            "HR_Workday": [
                "CreateEmployee", "UpdateCompensation", "EnrollBenefits", "ApproveTimeOff", "GetPerformanceReview",
                "OnboardNewHire", "UpdateOrgHierarchy", "ExportPayrollData", "SearchEmployee", "RecordTraining",
                "ProcessTermination", "SyncPayrollFinance", "ComplianceReport", "UpdateContactInfo", "PostJobRequisition",
                "HRAnalyticsReport", "ProcessPromotion", "EmployeeSurvey"
            ],
            "Logistics_Shipping": [
                "CreateShipment", "AssignCarrier", "GenerateLabel", "UpdateInTransit", "TrackShipment", "CustomsClearance",
                "CalculateFreightCost", "SyncWithSalesOrder", "WarehousePickPack", "ProcessReturn", "GetShipmentHistory",
                "OptimizeRoute", "DelayAlert", "ProofOfDelivery", "UpdateDCInventory", "FreightConsolidation",
                "LogisticsKPIReport", "InvoiceShippingCost"
            ],
            "Supply_Chain_Management": [
                "CreateSupplier", "OnboardSupplier", "CreatePurchaseRequisition", "ApprovePurchaseRequisition",
                "CreatePurchaseOrder", "SendPOToSupplier", "ReceiveASN", "BookGoodsReceipt", "QualityInspection",
                "ReleaseToInventory", "UpdateSupplierScorecard", "ForecastDemand", "RunMRP", "GeneratePlannedOrders",
                "ConvertToProductionOrder", "SafetyStockAlert", "ExcessInventoryAlert", "MultiEchelonInventoryOptimization",
                "SyncDemandWithCRM", "CreateInboundShipment", "TrackInboundETA", "SupplierPortalSync", "ContractManagement",
                "SpendAnalysisReport", "RiskMonitorSupplier", "SustainabilityComplianceCheck", "BlockchainTraceabilityUpdate",
                "SCKPIReport"
            ]
            }

            ### Rules for creating the plan:
            1. ALWAYS analyze the user's request and understand the end-to-end business goal.
            2. Create a deterministic sequence: For the exact same user question, you must always output the exact same list of tasks in the exact same order.
            3. Use ONLY task names that exist in the list above. Never invent new ones.
            4. Select the minimum number of tasks needed to fully achieve the goal.
            5. Follow logical business flow from start to finish (e.g., lead → order → procurement → production → shipping → invoice → payment).
            6. Include necessary checks, syncs, and approvals to make the process realistic.
            7. If data is needed from one system to another, include the relevant Sync tasks (e.g., SyncWithCRM, SyncWithSAP).
            8. Number the steps starting from 1.
            9. For each step, show: System name → Task name (a short 1-sentence plain-English explanation is optional but recommended).

            ### Output format (exactly like this, no extra text):
            Planned Tasks:
            1. Salesforce_CRM → CreateLead (Capture new prospect from website form)
            2. Salesforce_CRM → AssignLead (Auto-assign to regional sales rep)
            3. ...
            [continue until goal is fully achieved]

            Now, based on the user's question below, create the plan:

            User question: {query}

            please respond as JSON array of objects with "system", "task", and "description" properties.
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
            #.add_agent(ideation_agent, id="ideation_agent")
            #.add_agent(inquiry_agent, id="inquiry_agent", output_response=True)
            .set_start_executor(taskplanner_agent)
            #.add_edge(ideation_agent, inquiry_agent)
            #.add_edge(inquiry_agent, business_analyst)
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
                print(event.data)
                returntxt += event.data

        #chat_client.delete_agent(ideation_agent.id)
        #chat_client.delete_agent(inquiry_agent.id)
        # await chat_client.project_client.agents.delete_agent(ideation_agent.id)
        # await chat_client.project_client.agents.delete_agent(inquiry_agent.id)
        # chat_client.project_client.agents.threads.delete(ideation_agent.id)

    return returntxt

if __name__ == "__main__":
    #asyncio.run(create_agents())
    # query = "Create me a catchy phrase for humanoid enabling better remote work."
    query = "i would like to automate lead to cash process between salesforce and sap."
    tslist = asyncio.run(multi_agent_interaction(query))
    print("===== Planned Tasks =====")
    print(tslist)
    print("===== End =====")
    
    # Save tslist as JSON file
    try:
        # Try to parse the response as JSON if it's a string
        if isinstance(tslist, str):
            try:
                tslist_data = json.loads(tslist)
            except json.JSONDecodeError:
                # If it's not valid JSON, wrap it as plain text
                tslist_data = {"raw_output": tslist, "query": query}
        else:
            tslist_data = tslist
        
        # Create output filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"output/task_plan_{timestamp}.json"
        # output_file = f"output/task_plan_test.json"
        
        # Ensure output directory exists
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        
        # Save to file (overwrites if exists)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(tslist_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Task list saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Error saving JSON file: {e}")