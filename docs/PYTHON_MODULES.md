# Python Modules Documentation

## Table of Contents
1. [Core Agent Modules](#core-agent-modules)
2. [Multi-Agent Workflow Modules](#multi-agent-workflow-modules)
3. [Evaluation & Testing Modules](#evaluation--testing-modules)
4. [Domain-Specific Agents](#domain-specific-agents)
5. [Utility & Support Modules](#utility--support-modules)

---

## Core Agent Modules

### agent1.py - Basic Azure AI Agent

**Purpose**: Demonstrates creating and using a basic Azure AI agent with Azure AI Projects.

```mermaid
graph TB
    subgraph "agent1.py Architecture"
        A[Main Function] --> B[Azure CLI Credentials]
        B --> C[AI Project Client]
        C --> D[Create Agent]
        D --> E[ChatAgent Instance]
        E --> F[Tool: get_weather]
        F --> G[Execute Query]
        G --> H[Stream Response]
        H --> I[Cleanup]
    end
    
    style D fill:#4CAF50
    style F fill:#2196F3
```

**Key Components**:
- **AzureCliCredential**: Authentication using Azure CLI
- **AIProjectClient**: Connection to Azure AI Projects
- **ChatAgent**: Chat-based agent with streaming
- **Tools**: Custom Python functions (e.g., get_weather)

**Flow**:
```mermaid
sequenceDiagram
    participant Main
    participant Credential
    participant ProjectClient
    participant Agent
    participant Tool
    
    Main->>Credential: Initialize Azure CLI auth
    Main->>ProjectClient: Create client with endpoint
    ProjectClient->>Agent: Create agent with model
    Main->>Agent: Register tool (get_weather)
    Main->>Agent: Run query
    Agent->>Tool: Execute tool call
    Tool-->>Agent: Return result
    Agent-->>Main: Stream response
    Main->>ProjectClient: Delete agent (cleanup)
```

**Use Cases**:
- Simple chat interactions
- Tool calling demonstrations
- Azure AI Projects integration testing

---

### stagent.py - Stateful Agent

**Purpose**: Similar to agent1.py but demonstrates stateful agent patterns.

```mermaid
graph TB
    subgraph "Stateful Agent Pattern"
        S1[Initialize Agent] --> S2[Maintain State]
        S2 --> S3[Execute Task]
        S3 --> S4[Update State]
        S4 --> S5[Next Task]
        S5 --> |Loop| S3
        S5 --> S6[Cleanup]
    end
```

**Key Features**:
- Agent persistence and reuse
- State management across multiple interactions
- Production deployment patterns

---

### multiagents.py - Multi-Agent Workflows

**Purpose**: Demonstrates coordinating multiple agents in a workflow pattern.

```mermaid
graph TB
    subgraph "Multi-Agent Workflow Architecture"
        MA[Workflow Builder] --> W1[Writer Agent]
        MA --> R1[Reviewer Agent]
        
        W1 --> |Output| R1
        
        subgraph "Writer Agent"
            W2[Instructions: Content Creation]
            W3[Task: Generate Content]
        end
        
        subgraph "Reviewer Agent"
            R2[Instructions: Review & Critique]
            R3[Task: Provide Feedback]
        end
        
        R1 --> OUT[Final Output]
    end
    
    style MA fill:#FF9800
    style W1 fill:#4CAF50
    style R1 fill:#2196F3
```

**Workflow Pattern**:
```mermaid
sequenceDiagram
    participant User
    participant Workflow
    participant Writer
    participant Reviewer
    
    User->>Workflow: Submit task
    Workflow->>Writer: Generate content
    Writer-->>Workflow: Draft content
    Workflow->>Reviewer: Review content
    Reviewer-->>Workflow: Feedback
    Workflow-->>User: Final output
    
    Note over Workflow: Streaming events throughout
```

**Key Concepts**:
- **WorkflowBuilder**: Orchestrates agent execution
- **Edge Connections**: Defines data flow between agents
- **Streaming Events**: Real-time progress updates (AgentRunUpdateEvent)
- **Workflow Output**: Final results aggregation

**Use Cases**:
- Content generation with review
- Multi-step analysis tasks
- Quality assurance workflows

---

## Multi-Agent Workflow Modules

### stretailadv.py - Retail Advisory Agent

**Purpose**: Financial and retail product advisory using multi-agent collaboration.

```mermaid
graph TB
    subgraph "Retail Advisory Architecture"
        UI[User Query] --> RA[Retail Agent]
        
        RA --> MCP[Microsoft Learn MCP]
        RA --> STOCK[Stock Data Tool]
        RA --> WEATHER[Weather Tool]
        RA --> SEARCH[File Search]
        
        MCP --> KB[Knowledge Base]
        STOCK --> API1[Yahoo Finance API]
        WEATHER --> API2[Weather API]
        SEARCH --> VS[Vector Store]
        
        RA --> RESP[Comprehensive Response]
    end
    
    style RA fill:#4CAF50
    style MCP fill:#2196F3
```

**Agent Capabilities**:
```mermaid
graph LR
    subgraph "Retail Agent Tools"
        T1[Product Knowledge] --> T2[Inventory Check]
        T3[Price Analysis] --> T4[Stock Data]
        T5[Weather Context] --> T6[Recommendations]
        T7[Document Search] --> T8[Policy Info]
    end
```

**Key Features**:
- **HostedMCPTool**: Microsoft Learn integration
- **HostedFileSearchTool**: Document retrieval
- **Custom Tools**: Stock data, weather information
- **Workflow Orchestration**: Multi-agent coordination

---

### stsupplychainmfg.py - Supply Chain & Manufacturing Agent

**Purpose**: Manufacturing process optimization and supply chain analysis.

```mermaid
graph TB
    subgraph "Supply Chain Agent Workflow"
        SCM[Supply Chain Agent] --> P1[Process Analysis]
        SCM --> P2[Inventory Optimization]
        SCM --> P3[Quality Control]
        SCM --> P4[Demand Forecasting]
        
        P1 --> D1[Sequential Workflows]
        P2 --> D1
        P3 --> D1
        P4 --> D1
        
        D1 --> OUT[Actionable Insights]
    end
    
    style SCM fill:#FF9800
```

**Use Cases**:
- Production planning optimization
- Supply chain bottleneck identification
- Quality assurance automation
- Demand forecasting

---

### stchiprca.py - Chip Manufacturing RCA

**Purpose**: Root cause analysis for semiconductor/chip manufacturing issues.

```mermaid
graph TB
    subgraph "RCA Agent Process"
        ISSUE[Manufacturing Issue] --> DATA[Data Collection Agent]
        DATA --> ANALYSIS[RCA Analysis Agent]
        
        ANALYSIS --> PROC[Process Expert]
        ANALYSIS --> QUAL[Quality Expert]
        ANALYSIS --> SUPP[Supply Chain Expert]
        
        PROC --> SYNTH[Synthesis Agent]
        QUAL --> SYNTH
        SUPP --> SYNTH
        
        SYNTH --> REPORT[RCA Report]
        SYNTH --> REC[Recommendations]
    end
    
    style ANALYSIS fill:#F44336
    style SYNTH fill:#4CAF50
```

**Key Capabilities**:
- Automated data aggregation
- Multi-perspective analysis
- Root cause identification
- Actionable recommendations

---

### stenggagent.py - Engineering Design Agent

**Purpose**: Engineering design analysis and visualization.

```mermaid
graph TB
    subgraph "Engineering Agent"
        ENG[Engineering Query] --> IMG[Image Analysis]
        IMG --> DESIGN[Design Review]
        DESIGN --> SPEC[Specification Check]
        SPEC --> REC[Design Recommendations]
    end
    
    style IMG fill:#2196F3
```

**Features**:
- Multi-modal content (text + images)
- Engineering drawing analysis
- Design specification validation
- Azure OpenAI Responses Client for vision

---

## Evaluation & Testing Modules

### agenteval.py - Agent Evaluation Framework

**Purpose**: Comprehensive evaluation of agent performance using Azure AI evaluation metrics.

```mermaid
graph TB
    subgraph "Evaluation Framework"
        EVAL[Evaluation Suite] --> SYS[System Evaluation]
        EVAL --> RAG[RAG Evaluation]
        EVAL --> PROC[Process Evaluation]
        
        SYS --> E1[Task Completion]
        SYS --> E2[Task Adherence]
        SYS --> E3[Intent Resolution]
        
        RAG --> E4[Groundedness]
        RAG --> E5[Relevance]
        
        PROC --> E6[Tool Call Accuracy]
        PROC --> E7[Tool Selection]
        PROC --> E8[Tool Input Accuracy]
        PROC --> E9[Tool Output Utilization]
        
        E1 --> REPORT[Evaluation Report]
        E2 --> REPORT
        E3 --> REPORT
        E4 --> REPORT
        E5 --> REPORT
        E6 --> REPORT
        E7 --> REPORT
        E8 --> REPORT
        E9 --> REPORT
    end
    
    style EVAL fill:#4CAF50
    style REPORT fill:#2196F3
```

**Evaluation Metrics**:
```mermaid
graph LR
    subgraph "System Metrics"
        S1[Task Completion: Did agent complete the task?]
        S2[Task Adherence: Did agent follow instructions?]
        S3[Intent Resolution: Was user intent understood?]
    end
    
    subgraph "RAG Metrics"
        R1[Groundedness: Are responses based on facts?]
        R2[Relevance: Are responses relevant to query?]
    end
    
    subgraph "Process Metrics"
        P1[Tool Call Accuracy: Correct tool usage?]
        P2[Tool Selection: Right tool chosen?]
        P3[Tool Input Accuracy: Correct parameters?]
        P4[Tool Output Utilization: Results used properly?]
    end
```

**Evaluation Flow**:
```mermaid
sequenceDiagram
    participant Test
    participant EvalGroup
    participant EvalRun
    participant Evaluators
    participant Report
    
    Test->>EvalGroup: Create evaluation group
    Test->>EvalRun: Create eval run with test data
    EvalRun->>Evaluators: Execute evaluators
    
    par Parallel Evaluation
        Evaluators->>Evaluators: System metrics
        Evaluators->>Evaluators: RAG metrics
        Evaluators->>Evaluators: Process metrics
    end
    
    Evaluators-->>Report: Aggregate results
    Report-->>Test: Final scores & report URL
```

**Key Components**:
- **Data Source Config**: Custom schema for agent conversations
- **Testing Criteria**: Built-in Azure AI evaluators
- **Inline Data**: JSONL format for test cases
- **Output Items**: Detailed evaluation results per test case

---

### redteam.py - Red Team Safety Testing

**Purpose**: Security and safety vulnerability testing for AI agents.

```mermaid
graph TB
    subgraph "Red Team Testing Architecture"
        RT[Red Team Framework] --> AGENT[Target Agent]
        RT --> TAX[Taxonomy Generation]
        RT --> ATTACK[Attack Strategies]
        
        TAX --> RISKS[Risk Categories]
        RISKS --> R1[Prohibited Actions]
        RISKS --> R2[Self Harm]
        RISKS --> R3[Violence]
        RISKS --> R4[Sexual Content]
        RISKS --> R5[Hate/Unfairness]
        RISKS --> R6[Data Leakage]
        
        ATTACK --> A1[Flip Strategy]
        ATTACK --> A2[Base64 Encoding]
        ATTACK --> A3[Multi-turn Attacks]
        
        AGENT --> EVAL[Safety Evaluators]
        
        EVAL --> E1[Prohibited Actions Check]
        EVAL --> E2[Task Adherence Verify]
        EVAL --> E3[Data Leakage Detect]
        EVAL --> E4[Content Safety Check]
        
        E1 --> RESULTS[Test Results]
        E2 --> RESULTS
        E3 --> RESULTS
        E4 --> RESULTS
    end
    
    style RT fill:#F44336
    style EVAL fill:#FF9800
```

**Red Team Process**:
```mermaid
sequenceDiagram
    participant Test
    participant Agent
    participant Taxonomy
    participant RedTeam
    participant Evaluators
    
    Test->>Agent: Create agent version
    Test->>Taxonomy: Generate attack taxonomy
    Taxonomy-->>Test: Risk scenarios
    
    Test->>RedTeam: Create red team eval run
    RedTeam->>Agent: Execute attack strategies
    
    loop For each attack
        RedTeam->>Agent: Send adversarial prompt
        Agent-->>RedTeam: Agent response
        RedTeam->>Evaluators: Evaluate response
    end
    
    Evaluators-->>Test: Safety assessment
```

**Risk Categories Tested**:
- **Prohibited Actions**: Attempts to make agent perform forbidden tasks
- **Sensitive Data Leakage**: Extracting confidential information
- **Self Harm**: Promoting harmful behaviors
- **Violence**: Violent content generation
- **Sexual**: Inappropriate sexual content
- **Hate/Unfairness**: Discriminatory or biased responses

**Attack Strategies**:
- **Flip**: Reverse instructions
- **Base64**: Encode malicious prompts
- **Multi-turn**: Complex conversation attacks

---

### stagteval.py - Streamlit Agent Evaluation UI

**Purpose**: Interactive UI for running and visualizing agent evaluations.

```mermaid
graph TB
    subgraph "Evaluation UI"
        UI[Streamlit Interface] --> CONFIG[Configure Eval]
        CONFIG --> SELECT[Select Agent]
        SELECT --> RUN[Run Evaluation]
        RUN --> RESULTS[Display Results]
        RESULTS --> VIZ[Visualize Metrics]
    end
    
    style UI fill:#2196F3
```

---

## Domain-Specific Agents

### stsmartthings.py & stsmartthings_agent.py - SmartThings IoT Agents

**Purpose**: Control and manage Samsung SmartThings IoT devices through natural language.

```mermaid
graph TB
    subgraph "SmartThings Agent Architecture"
        USER[User Command] --> NLU[Natural Language Understanding]
        NLU --> INTENT[Intent Recognition]
        
        INTENT --> AGENT[SmartThings Agent]
        
        AGENT --> API[SmartThings API]
        API --> DEVICES[Device Control]
        
        DEVICES --> D1[Lights]
        DEVICES --> D2[Thermostat]
        DEVICES --> D3[Security]
        DEVICES --> D4[Appliances]
        
        D1 --> STATUS[Status Update]
        D2 --> STATUS
        D3 --> STATUS
        D4 --> STATUS
        
        STATUS --> USER
    end
    
    style AGENT fill:#4CAF50
    style API fill:#2196F3
```

**Capabilities**:
```mermaid
graph LR
    subgraph "Device Operations"
        O1[Turn On/Off] --> O2[Adjust Settings]
        O3[Query Status] --> O4[Create Automations]
        O5[Scene Control] --> O6[Energy Monitoring]
    end
```

**Integration Flow**:
```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant SmartThings
    participant Device
    
    User->>Agent: "Turn on living room lights"
    Agent->>Agent: Parse intent
    Agent->>SmartThings: Authenticate & list devices
    SmartThings-->>Agent: Device list
    Agent->>Agent: Identify target device
    Agent->>SmartThings: Send control command
    SmartThings->>Device: Execute command
    Device-->>SmartThings: Confirm status
    SmartThings-->>Agent: Status update
    Agent-->>User: "Living room lights are now on"
```

**Key Features**:
- **pysmartthings Integration**: Native Samsung API support
- **Multi-device Orchestration**: Control multiple devices simultaneously
- **Context-aware Commands**: Understanding room, device type, and state
- **Streamlit UI**: Interactive web interface

---

### stradiology.py - Medical Radiology Agent

**Purpose**: AI-assisted radiology analysis and report generation.

```mermaid
graph TB
    subgraph "Radiology Agent Workflow"
        IMG[Medical Image] --> UPLOAD[Image Upload]
        UPLOAD --> ANALYSIS[AI Image Analysis]
        
        ANALYSIS --> DETECT[Anomaly Detection]
        DETECT --> CLASS[Classification]
        CLASS --> PRIORITY[Priority Assessment]
        
        PRIORITY --> |Critical| URGENT[Urgent Review Flag]
        PRIORITY --> |Routine| QUEUE[Standard Queue]
        
        URGENT --> REPORT[AI-Assisted Report]
        QUEUE --> REPORT
        
        REPORT --> RADIOLOGIST[Radiologist Review]
    end
    
    style ANALYSIS fill:#F44336
    style DETECT fill:#FF9800
```

**Use Cases**:
- Automated image pre-screening
- Anomaly detection and flagging
- Report generation assistance
- Priority-based workflow optimization

---

### stbrainstorm.py - Brainstorming Agent

**Purpose**: Collaborative ideation and creative problem-solving.

```mermaid
graph TB
    subgraph "Brainstorming Workflow"
        TOPIC[Topic/Problem] --> AGENT[Brainstorm Agent]
        
        AGENT --> IDEATE[Idea Generation]
        IDEATE --> EXPAND[Idea Expansion]
        EXPAND --> CRITIQUE[Critical Analysis]
        CRITIQUE --> REFINE[Refinement]
        
        REFINE --> OUTPUT[Structured Ideas]
    end
    
    style AGENT fill:#9C27B0
```

---

### stocks.py & foundryiq.py - Financial & Knowledge Base Agents

**Purpose**: Financial data analysis and knowledge base querying.

**stocks.py - Financial Analysis**:
```mermaid
graph TB
    subgraph "Stock Analysis Agent"
        QUERY[Stock Query] --> FETCH[Fetch Market Data]
        FETCH --> ANALYZE[Technical Analysis]
        ANALYZE --> INSIGHTS[Generate Insights]
        INSIGHTS --> REC[Recommendations]
    end
    
    style ANALYZE fill:#4CAF50
```

**foundryiq.py - Knowledge Base RAG**:
```mermaid
graph TB
    subgraph "Foundry IQ Agent"
        Q[User Question] --> SEARCH[Azure AI Search]
        SEARCH --> RETRIEVE[Agentic Retrieval]
        RETRIEVE --> REASON[Query Planning]
        REASON --> CONTEXT[Relevant Context]
        CONTEXT --> AGENT[Chat Agent]
        AGENT --> ANSWER[Grounded Answer]
    end
    
    style SEARCH fill:#2196F3
    style RETRIEVE fill:#4CAF50
```

**Key Features**:
- **Agentic Retrieval**: Advanced query planning with reasoning effort
- **Vector Search**: Semantic search across knowledge base
- **Grounded Responses**: Answers based on retrieved documents
- **Managed Identity**: Secure, keyless authentication

---

## Utility & Support Modules

### utils.py - Common Utilities

**Purpose**: Shared utility functions used across multiple agents.

```mermaid
graph LR
    subgraph "Utility Functions"
        U1[get_weather] --> U2[Weather API Call]
        U3[fetch_stock_data] --> U4[Financial Data API]
        U5[Data Processing] --> U6[Format Conversion]
    end
```

**Common Functions**:
- **get_weather()**: Fetches weather information for locations
- **fetch_stock_data()**: Retrieves stock market data
- Data formatting and transformation helpers

---

### agentobs.py - Observability Setup

**Purpose**: OpenTelemetry instrumentation for agent monitoring.

```mermaid
graph TB
    subgraph "Observability Architecture"
        AGENT[Agent Execution] --> TRACER[OpenTelemetry Tracer]
        TRACER --> SPANS[Trace Spans]
        
        SPANS --> AZURE[Azure Monitor]
        AZURE --> INSIGHTS[Application Insights]
        
        INSIGHTS --> METRICS[Performance Metrics]
        INSIGHTS --> TRACES[Distributed Traces]
        INSIGHTS --> LOGS[Structured Logs]
    end
    
    style TRACER fill:#FF9800
    style AZURE fill:#2196F3
```

**Capabilities**:
- Distributed tracing across agent calls
- Performance monitoring
- Error tracking
- Custom span creation

---

### streamlit_ui.py & devui.py - User Interfaces

**Purpose**: Interactive web interfaces for agent interaction.

```mermaid
graph TB
    subgraph "Streamlit UI Architecture"
        UI[Streamlit App] --> STATE[Session State]
        STATE --> CHAT[Chat Interface]
        
        CHAT --> INPUT[User Input]
        INPUT --> AGENT[Agent Backend]
        AGENT --> STREAM[Response Streaming]
        STREAM --> DISPLAY[Live Display]
        
        DISPLAY --> HISTORY[Chat History]
    end
    
    style UI fill:#FF4B4B
```

**Features**:
- Real-time chat interface
- Message history management
- File upload support
- Response streaming visualization

---

### exagent.py - Existing Agent Consumption

**Purpose**: Demonstrates consuming pre-existing agents from Azure AI Projects.

```mermaid
graph LR
    subgraph "Agent Reuse Pattern"
        P[Portal/CLI] --> CREATE[Create Agent]
        CREATE --> ID[Agent ID]
        ID --> REUSE[Reuse in Code]
        REUSE --> EXEC[Execute Tasks]
    end
```

**Use Cases**:
- Production agent reuse
- Agent lifecycle management
- Multi-environment deployment

---

### samsung_smartthings_mcp.py - SmartThings MCP Server

**Purpose**: MCP (Model Context Protocol) server for SmartThings integration.

```mermaid
graph TB
    subgraph "MCP Server Architecture"
        MCP[MCP Server] --> PROTO[Protocol Handler]
        PROTO --> TOOLS[Tool Definitions]
        
        TOOLS --> T1[Device List]
        TOOLS --> T2[Device Control]
        TOOLS --> T3[Status Query]
        
        T1 --> ST[SmartThings API]
        T2 --> ST
        T3 --> ST
    end
    
    style MCP fill:#9C27B0
```

---

## Module Dependencies

```mermaid
graph TB
    subgraph "Core Dependencies"
        CORE[agent-framework] --> AZURE[agent-framework-azure-ai]
        AZURE --> SEARCH[agent-framework-azure-ai-search]
        CORE --> VIZ[agent-framework-viz]
    end
    
    subgraph "Azure Services"
        AOAI[Azure OpenAI]
        PROJECTS[Azure AI Projects]
        AISEARCH[Azure AI Search]
        MONITOR[Azure Monitor]
    end
    
    subgraph "Data & Analytics"
        PANDAS[pandas]
        YFINANCE[yfinance]
        DUCKDB[duckdb]
    end
    
    subgraph "UI & Presentation"
        STREAMLIT[streamlit]
        DEVUI[agent-framework-devui]
    end
    
    AZURE --> AOAI
    AZURE --> PROJECTS
    SEARCH --> AISEARCH
    VIZ --> MONITOR
    
    style CORE fill:#4CAF50
    style AZURE fill:#2196F3
```

## Summary

The Microsoft Agent Framework provides a comprehensive suite of modules organized into:

1. **Core Agents**: Basic building blocks for agent creation
2. **Workflows**: Multi-agent orchestration and collaboration
3. **Evaluation**: Quality assurance and safety testing
4. **Domain Agents**: Specialized implementations for specific industries
5. **Utilities**: Supporting functions and infrastructure

Each module is designed for modularity, reusability, and scalability, enabling rapid development of production-grade AI agent applications.
