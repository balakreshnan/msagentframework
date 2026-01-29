# Microsoft Agent Framework - Architecture Documentation

## Overview

The Microsoft Agent Framework (msagentframework) is a comprehensive platform for building, deploying, and managing AI agents using Azure AI services. This framework leverages the power of Large Language Models (LLMs) and agentic AI to transform how businesses approach complex workflows across multiple domains including retail, manufacturing, healthcare, IoT, and more.

## System Architecture

```mermaid
graph TB
    subgraph "User Interface Layer"
        UI1[Streamlit UI]
        UI2[DevUI]
        UI3[Domain-Specific UIs]
    end
    
    subgraph "Agent Framework Core"
        AF[Agent Framework]
        AC[Azure AI Agent Client]
        WF[Workflow Builder]
        MT[Multi-Agent System]
    end
    
    subgraph "Agent Types"
        CA[Chat Agents]
        WA[Workflow Agents]
        SA[Specialized Agents]
        MA[Multi-Agent Workflows]
    end
    
    subgraph "Azure AI Services"
        AOAI[Azure OpenAI]
        AIP[Azure AI Projects]
        AIS[Azure AI Search]
        AIM[Azure AI Monitoring]
    end
    
    subgraph "Domain-Specific Implementations"
        RT[Retail Advisor]
        SC[Supply Chain & Manufacturing]
        ST[SmartThings IoT]
        HC[Healthcare/Radiology]
        FA[Financial Advisor]
    end
    
    subgraph "Evaluation & Safety"
        EV[Agent Evaluation]
        RT_EVAL[Red Team Testing]
        OBS[Observability]
    end
    
    subgraph "Tools & Integrations"
        MCP[MCP Tools]
        FS[File Search]
        VS[Vector Store]
        API[External APIs]
    end
    
    UI1 --> AF
    UI2 --> AF
    UI3 --> AF
    
    AF --> AC
    AF --> WF
    AF --> MT
    
    AC --> CA
    WF --> WA
    MT --> MA
    CA --> SA
    
    AC --> AOAI
    AC --> AIP
    AC --> AIS
    AC --> AIM
    
    SA --> RT
    SA --> SC
    SA --> ST
    SA --> HC
    SA --> FA
    
    AF --> EV
    AF --> RT_EVAL
    AF --> OBS
    
    CA --> MCP
    CA --> FS
    CA --> VS
    CA --> API
    
    style AF fill:#4CAF50
    style AC fill:#2196F3
    style AOAI fill:#FF9800
    style EV fill:#F44336
```

## High-Level Component Architecture

```mermaid
graph LR
    subgraph "Application Layer"
        A1[Domain Applications]
        A2[Interactive UIs]
        A3[Workflow Engines]
    end
    
    subgraph "Agent Framework Layer"
        B1[Chat Agent API]
        B2[Workflow Builder]
        B3[Agent Client]
        B4[Context Providers]
    end
    
    subgraph "Infrastructure Layer"
        C1[Azure AI Projects]
        C2[Azure OpenAI]
        C3[Azure AI Search]
        C4[Azure Monitor]
    end
    
    subgraph "Data & Tools Layer"
        D1[Vector Stores]
        D2[MCP Tools]
        D3[File Search]
        D4[External APIs]
    end
    
    A1 --> B1
    A2 --> B2
    A3 --> B3
    
    B1 --> C1
    B2 --> C2
    B3 --> C3
    B4 --> C4
    
    B1 --> D1
    B2 --> D2
    B3 --> D3
    B4 --> D4
```

## Core Components

### 1. Agent Framework Core

The framework provides essential building blocks for creating AI agents:

- **ChatAgent**: Asynchronous chat-based agents with streaming support
- **WorkflowBuilder**: Orchestrates multi-agent workflows with sequential and parallel execution
- **AzureAIAgentClient**: Connects agents to Azure AI infrastructure
- **Context Providers**: Supplies agents with real-time data and knowledge

### 2. Multi-Agent System

Enables coordination between multiple specialized agents:

- **Writer-Reviewer Pattern**: Content generation with iterative feedback
- **Sequential Workflows**: Chain agents for complex multi-step tasks
- **Parallel Execution**: Run independent agent tasks concurrently
- **Event Streaming**: Real-time updates from agent execution

### 3. Evaluation & Safety Framework

Comprehensive testing and validation:

- **Agent Evaluation**: System, RAG, and process evaluation metrics
- **Red Team Testing**: Security and safety vulnerability scanning
- **Observability**: OpenTelemetry integration for tracing and monitoring
- **Quality Metrics**: Task completion, adherence, groundedness, relevance

### 4. Domain-Specific Agents

Pre-built agents for specific business domains:

- **Retail Advisor**: Product recommendations, inventory management
- **Supply Chain & Manufacturing**: Process optimization, RCA analysis
- **SmartThings IoT**: Device control and automation
- **Healthcare**: Radiology analysis, medical imaging
- **Financial Services**: Stock analysis, portfolio management

## Technology Stack

```mermaid
graph TB
    subgraph "Languages & Frameworks"
        PY[Python 3.12+]
        ST[Streamlit]
        ASYNC[AsyncIO]
    end
    
    subgraph "Azure Services"
        AOAI[Azure OpenAI]
        AIPROJ[Azure AI Projects]
        AISRCH[Azure AI Search]
        AIMON[Azure Monitor]
        AID[Azure Identity]
    end
    
    subgraph "Agent Libraries"
        AF[agent-framework]
        AFAZ[agent-framework-azure-ai]
        AFUI[agent-framework-devui]
        AFVIZ[agent-framework viz]
        AFSRCH[agent-framework-azure-ai-search]
    end
    
    subgraph "Data & Analytics"
        PD[pandas]
        YF[yfinance]
        DDB[duckdb]
    end
    
    subgraph "Security & Testing"
        PYRIT[PyRIT]
        AZEVAL[azure-ai-evaluation]
    end
    
    subgraph "Integrations"
        ST_API[pysmartthings]
        OTEL[OpenTelemetry]
        MCP[MCP Server]
    end
    
    PY --> AF
    ST --> AFUI
    ASYNC --> AF
    
    AID --> AOAI
    AID --> AIPROJ
    
    AF --> AFAZ
    AFAZ --> AOAI
    AFAZ --> AIPROJ
    AFAZ --> AISRCH
    
    AFVIZ --> AFUI
    AFSRCH --> AISRCH
    
    style AOAI fill:#FF9800
    style AF fill:#4CAF50
    style PYRIT fill:#F44336
```

## Data Flow Architecture

```mermaid
sequenceDiagram
    participant User
    participant UI as User Interface
    participant Agent as Chat Agent
    participant Client as Azure AI Client
    participant LLM as Azure OpenAI
    participant Tools as Tools/APIs
    participant Search as Vector Search
    
    User->>UI: Submit Query
    UI->>Agent: Create Agent Request
    Agent->>Client: Initialize Agent
    Client->>LLM: Create Agent Instance
    
    Agent->>Search: Retrieve Context
    Search-->>Agent: Relevant Documents
    
    Agent->>LLM: Send Query + Context
    LLM->>Tools: Execute Tool Calls
    Tools-->>LLM: Tool Results
    
    LLM-->>Agent: Stream Response
    Agent-->>UI: Stream Updates
    UI-->>User: Display Results
    
    Note over Agent,LLM: Observability traces all steps
```

## Security Architecture

```mermaid
graph TB
    subgraph "Security Layers"
        AUTH[Azure Authentication]
        RBAC[Role-Based Access]
        SECRETS[Secret Management]
    end
    
    subgraph "Evaluation Framework"
        REDTEAM[Red Team Testing]
        SAFETY[Safety Evaluators]
        MONITORING[Security Monitoring]
    end
    
    subgraph "Data Protection"
        ENCRYPT[Data Encryption]
        PRIVACY[PII Detection]
        AUDIT[Audit Logging]
    end
    
    AUTH --> RBAC
    RBAC --> SECRETS
    
    REDTEAM --> SAFETY
    SAFETY --> MONITORING
    
    ENCRYPT --> PRIVACY
    PRIVACY --> AUDIT
    
    RBAC --> REDTEAM
    SECRETS --> ENCRYPT
    MONITORING --> AUDIT
    
    style REDTEAM fill:#F44336
    style AUTH fill:#4CAF50
    style ENCRYPT fill:#2196F3
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Development"
        DEV[Local Development]
        TEST[Testing Environment]
    end
    
    subgraph "CI/CD Pipeline"
        GH[GitHub Actions]
        BUILD[Build & Test]
        EVAL[Agent Evaluation]
        REDTEAM[Red Team Tests]
    end
    
    subgraph "Production"
        PROD[Production Environment]
        MONITOR[Monitoring & Alerts]
        SCALE[Auto-scaling]
    end
    
    DEV --> GH
    GH --> BUILD
    BUILD --> EVAL
    EVAL --> REDTEAM
    REDTEAM --> PROD
    PROD --> MONITOR
    MONITOR --> SCALE
    
    style GH fill:#2196F3
    style PROD fill:#4CAF50
    style REDTEAM fill:#F44336
```

## Key Design Principles

### 1. **Asynchronous by Default**
All agent operations use Python's asyncio for non-blocking execution and high concurrency.

### 2. **Context-Aware Processing**
Agents can access multiple context providers (vector search, file stores, APIs) to enhance responses.

### 3. **Streaming-First**
Real-time streaming of agent responses for better user experience and responsiveness.

### 4. **Observability Built-In**
OpenTelemetry integration provides complete visibility into agent execution and performance.

### 5. **Safety & Evaluation**
Comprehensive testing framework ensures agents are safe, accurate, and reliable.

### 6. **Domain-Specific Extensibility**
Easy to create specialized agents for specific business domains and use cases.

## Integration Points

### Azure AI Services
- **Azure OpenAI**: LLM inference and embeddings
- **Azure AI Projects**: Agent lifecycle management
- **Azure AI Search**: Knowledge base and vector search
- **Azure Monitor**: Application insights and telemetry

### External Tools
- **MCP Tools**: Microsoft Learn, documentation access
- **File Search**: Document retrieval and analysis
- **Vector Stores**: Semantic search capabilities
- **REST APIs**: External data sources and services

### Authentication
- **Azure CLI Credentials**: Development authentication
- **Managed Identity**: Production secure access
- **Service Principals**: Application-to-application auth

## Scalability & Performance

### Horizontal Scaling
- Multiple agent instances can run in parallel
- Workflow builders support concurrent agent execution
- Load balancing across Azure AI deployments

### Caching & Optimization
- Context provider caching
- Vector store optimization
- Response streaming for better perceived performance

### Resource Management
- Async context managers for proper cleanup
- Connection pooling for Azure services
- Automatic retry and error handling
