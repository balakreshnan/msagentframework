# GitHub Workflows Documentation

## Overview

The repository uses GitHub Actions for Continuous Integration and Continuous Deployment (CI/CD). The workflows automate agent deployment, testing, evaluation, and security validation.

## Workflow Architecture

```mermaid
graph TB
    subgraph "GitHub Actions Pipeline"
        TRIGGER[Workflow Trigger] --> CHECKOUT[Checkout Code]
        CHECKOUT --> SETUP[Setup Environment]
        SETUP --> DEPS[Install Dependencies]
        DEPS --> AUTH[Azure Authentication]
        
        AUTH --> EXEC[Execute Agent]
        EXEC --> EVAL[Run Evaluation]
        EVAL --> REDTEAM[Red Team Testing]
        
        REDTEAM --> |Pass| SUCCESS[Deployment Success]
        REDTEAM --> |Fail| FAILURE[Block Deployment]
    end
    
    style EXEC fill:#4CAF50
    style EVAL fill:#2196F3
    style REDTEAM fill:#F44336
    style FAILURE fill:#FF5252
```

## agent-consumption-single-env.yml

**Purpose**: Consumes and tests an existing Azure AI agent in a single environment (dev).

### Workflow Configuration

```yaml
name: Agent Consumption - Single Environment
on:
  workflow_dispatch:  # Manual trigger only
```

**Trigger Type**: Manual (`workflow_dispatch`)
- Provides controlled deployment
- Allows on-demand testing
- Prevents accidental executions

### Workflow Structure

```mermaid
graph TB
    subgraph "Workflow Jobs"
        JOB[consume-agent Job] --> ENV[Environment: dev]
        ENV --> RUNNER[Runs on: ubuntu-latest]
        
        RUNNER --> STEPS[Workflow Steps]
    end
    
    subgraph "Execution Steps"
        S1[1. Checkout Repository]
        S2[2. Setup Python 3.12]
        S3[3. Install Dependencies]
        S4[4. Azure Login]
        S5[5. Run Agent Test]
        S6[6. Run Evaluation]
        S7[7. Run Red Team Tests]
    end
    
    STEPS --> S1
    S1 --> S2
    S2 --> S3
    S3 --> S4
    S4 --> S5
    S5 --> S6
    S6 --> S7
```

### Step-by-Step Breakdown

#### Step 1: Checkout Repository

```yaml
- name: Checkout repo
  uses: actions/checkout@v4
```

```mermaid
graph LR
    A[GitHub Actions] --> B[Clone Repository]
    B --> C[Checkout Branch]
    C --> D[Prepare Workspace]
```

**Purpose**:
- Downloads repository code
- Provides access to Python scripts
- Ensures latest code version

---

#### Step 2: Setup Python Environment

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: "3.12"
```

```mermaid
graph LR
    A[Setup Action] --> B[Install Python 3.12]
    B --> C[Configure PATH]
    C --> D[Verify Installation]
```

**Purpose**:
- Installs Python 3.12 runtime
- Configures environment variables
- Ensures compatibility with agent framework

---

#### Step 3: Install Dependencies

```yaml
- name: Install dependencies
  run: |
    pip install -r requirements.txt
```

```mermaid
graph TB
    REQ[requirements.txt] --> PIP[pip install]
    PIP --> PKG1[agent-framework]
    PIP --> PKG2[azure-ai-projects]
    PIP --> PKG3[streamlit]
    PIP --> PKG4[Other dependencies]
    
    PKG1 --> ENV[Python Environment]
    PKG2 --> ENV
    PKG3 --> ENV
    PKG4 --> ENV
```

**Dependencies Installed**:
- agent-framework and extensions
- Azure SDK packages
- Data processing libraries (pandas, yfinance, duckdb)
- Evaluation tools (azure-ai-evaluation, pyrit)
- UI frameworks (streamlit)

---

#### Step 4: Azure Authentication

```yaml
- name: Azure login
  uses: azure/login@v1
  with:
    creds: ${{ secrets.AZURE_CREDENTIALS }}
```

```mermaid
graph TB
    subgraph "Authentication Flow"
        SECRET[GitHub Secret: AZURE_CREDENTIALS] --> ACTION[Azure Login Action]
        ACTION --> SP[Service Principal Auth]
        SP --> TOKEN[Access Token]
        TOKEN --> AZURE[Azure Resources]
    end
    
    style SECRET fill:#FFC107
    style TOKEN fill:#4CAF50
```

**Purpose**:
- Authenticates with Azure using service principal
- Grants access to Azure AI resources
- Enables secure resource operations

**Required Secret Format**:
```json
{
  "clientId": "<service-principal-client-id>",
  "clientSecret": "<service-principal-secret>",
  "subscriptionId": "<azure-subscription-id>",
  "tenantId": "<azure-tenant-id>"
}
```

---

#### Step 5: Run Agent Execution Test

```yaml
- name: Run agent execution test
  env:
    AZURE_AI_PROJECT: ${{ secrets.AZURE_AI_PROJECT }}
    AZURE_AI_PROJECT_ENDPOINT: ${{ secrets.AZURE_AI_PROJECT_ENDPOINT }}
    AZURE_OPENAI_KEY: ${{ secrets.AZURE_OPENAI_KEY }}
    AZURE_OPENAI_ENDPOINT: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
    # ... additional environment variables
  run: |
    python exagent.py \
      --resource-group "${{ secrets.AZURE_RESOURCE_GROUP }}" \
      --project "${{ secrets.AZURE_AI_PROJECT }}" \
      --agent-name "${{ secrets.AGENT_NAME }}"
```

```mermaid
sequenceDiagram
    participant Workflow
    participant Script as exagent.py
    participant Azure as Azure AI Projects
    participant Agent
    
    Workflow->>Script: Execute with parameters
    Script->>Azure: Authenticate
    Azure-->>Script: Access granted
    Script->>Agent: Load existing agent
    Agent-->>Script: Agent instance
    Script->>Agent: Execute test queries
    Agent-->>Script: Responses
    Script-->>Workflow: Test results (exit code)
```

**Purpose**:
- Tests agent functionality
- Validates connectivity to Azure
- Ensures agent responds correctly
- Verifies tool calling capabilities

**Environment Variables Used**:
- `AZURE_AI_PROJECT`: Azure AI project name
- `AZURE_AI_PROJECT_ENDPOINT`: Project API endpoint
- `AZURE_OPENAI_KEY`: OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: OpenAI service endpoint
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: Model deployment name
- `AZURE_OPENAI_DEPLOYMENT`: Deployment identifier

---

#### Step 6: Run Evaluation

```yaml
- name: Run evaluation
  env:
    # Same environment variables as Step 5
  run: |
    python agenteval.py \
      --resource-group "${{ secrets.AZURE_RESOURCE_GROUP }}" \
      --project "${{ secrets.AZURE_AI_PROJECT }}" \
      --agent-name "${{ secrets.AGENT_NAME }}"
```

```mermaid
graph TB
    subgraph "Evaluation Process"
        START[agenteval.py] --> CREATE[Create Eval Group]
        CREATE --> CONFIG[Configure Evaluators]
        
        CONFIG --> SYS[System Evaluators]
        CONFIG --> RAG[RAG Evaluators]
        CONFIG --> PROC[Process Evaluators]
        
        SYS --> E1[Task Completion]
        SYS --> E2[Task Adherence]
        SYS --> E3[Intent Resolution]
        
        RAG --> E4[Groundedness]
        RAG --> E5[Relevance]
        
        PROC --> E6[Tool Call Accuracy]
        PROC --> E7[Tool Selection]
        PROC --> E8[Tool Input Accuracy]
        PROC --> E9[Tool Output Utilization]
        
        E1 --> RUN[Create Eval Run]
        E2 --> RUN
        E3 --> RUN
        E4 --> RUN
        E5 --> RUN
        E6 --> RUN
        E7 --> RUN
        E8 --> RUN
        E9 --> RUN
        
        RUN --> EXECUTE[Execute Tests]
        EXECUTE --> RESULTS[Collect Results]
        RESULTS --> REPORT[Generate Report]
    end
    
    style E1 fill:#4CAF50
    style E4 fill:#2196F3
    style E6 fill:#FF9800
    style REPORT fill:#9C27B0
```

**Evaluation Metrics**:

| Category | Metric | Purpose |
|----------|--------|---------|
| System | Task Completion | Verify task was completed |
| System | Task Adherence | Check instruction following |
| System | Intent Resolution | Validate intent understanding |
| RAG | Groundedness | Ensure factual responses |
| RAG | Relevance | Check response relevance |
| Process | Tool Call Accuracy | Validate correct tool usage |
| Process | Tool Selection | Assess tool choice appropriateness |
| Process | Tool Input Accuracy | Check parameter correctness |
| Process | Tool Output Utilization | Verify result usage |

**Output**:
- Evaluation scores for each metric
- Report URL for detailed analysis
- Pass/fail status

---

#### Step 7: Run Red Team Tests

```yaml
- name: Run red team tests (optional)
  env:
    # Same environment variables
  run: |
    python redteam.py \
      --resource-group "${{ secrets.AZURE_RESOURCE_GROUP }}" \
      --project "${{ secrets.AZURE_AI_PROJECT }}" \
      --agent-name "${{ secrets.AGENT_NAME }}"
```

```mermaid
graph TB
    subgraph "Red Team Testing Process"
        START[redteam.py] --> VERSION[Create Agent Version]
        VERSION --> TAX[Generate Taxonomy]
        
        TAX --> RISKS[Define Risk Categories]
        RISKS --> R1[Prohibited Actions]
        RISKS --> R2[Self Harm]
        RISKS --> R3[Violence]
        RISKS --> R4[Sexual Content]
        RISKS --> R5[Hate/Unfairness]
        RISKS --> R6[Data Leakage]
        
        R1 --> EVAL[Create Red Team Eval]
        R2 --> EVAL
        R3 --> EVAL
        R4 --> EVAL
        R5 --> EVAL
        R6 --> EVAL
        
        EVAL --> ATTACK[Execute Attack Strategies]
        
        ATTACK --> A1[Flip Strategy]
        ATTACK --> A2[Base64 Encoding]
        ATTACK --> A3[Multi-turn Attacks]
        
        A1 --> RUN[Run Eval]
        A2 --> RUN
        A3 --> RUN
        
        RUN --> ASSESS[Safety Assessment]
        ASSESS --> OUTPUT[Test Results]
    end
    
    style RISKS fill:#F44336
    style ATTACK fill:#FF5252
    style ASSESS fill:#FF9800
```

**Security Testing**:

```mermaid
sequenceDiagram
    participant RT as Red Team Test
    participant Agent
    participant Evaluators
    participant Results
    
    RT->>Agent: Create agent version
    RT->>RT: Generate attack taxonomy
    
    loop For each risk category
        RT->>Agent: Send adversarial prompt (Flip)
        Agent-->>RT: Response
        RT->>Evaluators: Evaluate safety
        
        RT->>Agent: Send encoded prompt (Base64)
        Agent-->>RT: Response
        RT->>Evaluators: Evaluate safety
        
        RT->>Agent: Multi-turn attack
        Agent-->>RT: Response
        RT->>Evaluators: Evaluate safety
    end
    
    Evaluators-->>Results: Safety scores
    Results-->>RT: Pass/Fail determination
```

**Red Team Evaluators**:
1. **Prohibited Actions**: Attempts to bypass restrictions
2. **Task Adherence**: Ensures agent stays on task during attacks
3. **Sensitive Data Leakage**: Tests for information disclosure
4. **Self Harm**: Checks for harmful content generation
5. **Violence**: Tests violent content filtering
6. **Sexual**: Validates inappropriate content blocking
7. **Hate/Unfairness**: Tests for bias and discrimination

**Attack Strategies**:
- **Flip**: Reverses or negates instructions
- **Base64**: Encodes malicious prompts to bypass filters
- **Multi-turn**: Complex multi-step conversation attacks

**Output Artifacts**:
- `taxonomy_{agent_name}.json`: Attack taxonomy
- `redteam_eval_output_items_{agent_name}.json`: Detailed results
- Safety assessment report

---

## Workflow Secrets Configuration

### Required Secrets

```mermaid
graph TB
    subgraph "GitHub Secrets"
        S1[AZURE_CREDENTIALS]
        S2[AZURE_RESOURCE_GROUP]
        S3[AZURE_AI_PROJECT]
        S4[AZURE_AI_PROJECT_ENDPOINT]
        S5[AZURE_OPENAI_KEY]
        S6[AZURE_OPENAI_ENDPOINT]
        S7[AZURE_AI_MODEL_DEPLOYMENT_NAME]
        S8[AZURE_OPENAI_DEPLOYMENT]
        S9[AGENT_NAME]
    end
    
    subgraph "Usage"
        U1[Authentication]
        U2[Resource Identification]
        U3[API Access]
        U4[Agent Selection]
    end
    
    S1 --> U1
    S2 --> U2
    S3 --> U2
    S4 --> U2
    S5 --> U3
    S6 --> U3
    S7 --> U3
    S8 --> U3
    S9 --> U4
    
    style S1 fill:#FFC107
    style S5 fill:#FFC107
```

| Secret | Description | Example Format |
|--------|-------------|----------------|
| `AZURE_CREDENTIALS` | Service principal JSON | `{"clientId":"...","clientSecret":"...","subscriptionId":"...","tenantId":"..."}` |
| `AZURE_RESOURCE_GROUP` | Resource group name | `my-ai-agents-rg` |
| `AZURE_AI_PROJECT` | AI project name | `my-agent-project` |
| `AZURE_AI_PROJECT_ENDPOINT` | Project endpoint URL | `https://account.services.ai.azure.com/api/projects/project-name` |
| `AZURE_OPENAI_KEY` | OpenAI API key | `abc123...` |
| `AZURE_OPENAI_ENDPOINT` | OpenAI endpoint | `https://my-openai.openai.azure.com` |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment | `gpt-4o` |
| `AZURE_OPENAI_DEPLOYMENT` | OpenAI deployment ID | `gpt-4o-deployment` |
| `AGENT_NAME` | Target agent name | `CustomerServiceAgent` |

---

## Workflow Execution Flow

```mermaid
stateDiagram-v2
    [*] --> Triggered: Manual Dispatch
    Triggered --> Checkout: Clone Repo
    Checkout --> Setup: Python 3.12
    Setup --> Install: pip install
    Install --> Auth: Azure Login
    
    Auth --> AgentTest: Run exagent.py
    AgentTest --> Evaluation: Run agenteval.py
    Evaluation --> RedTeam: Run redteam.py
    
    AgentTest --> Failed: Test Failure
    Evaluation --> Failed: Eval Failure
    RedTeam --> Failed: Security Issue
    
    RedTeam --> Success: All Passed
    Failed --> [*]
    Success --> [*]
```

---

## Best Practices

### 1. Environment Isolation

```mermaid
graph LR
    subgraph "Environment Strategy"
        DEV[Development Env] --> TEST[Test Env]
        TEST --> STAGING[Staging Env]
        STAGING --> PROD[Production Env]
    end
    
    subgraph "Workflow Usage"
        DEV --> W1[dev workflow]
        TEST --> W2[test workflow]
        STAGING --> W3[staging workflow]
        PROD --> W4[prod workflow]
    end
```

**Recommendation**: Create separate workflows for each environment:
- `agent-consumption-dev.yml`
- `agent-consumption-test.yml`
- `agent-consumption-staging.yml`
- `agent-consumption-prod.yml`

### 2. Secret Management

```mermaid
graph TB
    subgraph "Secret Rotation"
        S1[Secret Created] --> S2[Regular Rotation]
        S2 --> S3[Update GitHub]
        S3 --> S4[Test Workflow]
        S4 --> S5[Old Secret Deprecated]
    end
```

**Guidelines**:
- Rotate secrets every 90 days
- Use Azure Key Vault for production
- Never commit secrets to code
- Audit secret access regularly

### 3. Failure Handling

```mermaid
graph TB
    subgraph "Error Handling Strategy"
        E1[Step Fails] --> E2[Log Details]
        E2 --> E3[Notify Team]
        E3 --> E4[Investigate]
        E4 --> E5[Fix & Rerun]
    end
```

**Recommendations**:
- Enable workflow notifications
- Store artifacts on failure
- Implement retry logic for transient errors
- Log comprehensive error details

### 4. Performance Optimization

```mermaid
graph LR
    subgraph "Optimization Techniques"
        O1[Cache Dependencies] --> O2[Parallel Jobs]
        O2 --> O3[Conditional Steps]
        O3 --> O4[Matrix Strategy]
    end
```

**Techniques**:
- Cache pip dependencies
- Run independent jobs in parallel
- Skip optional steps on PR workflows
- Use matrix builds for multi-environment testing

---

## Monitoring & Observability

```mermaid
graph TB
    subgraph "Workflow Monitoring"
        W[Workflow Run] --> L[GitHub Logs]
        W --> A[Azure Monitor]
        W --> N[Notifications]
        
        L --> D1[Step Logs]
        A --> D2[Agent Traces]
        N --> D3[Team Alerts]
        
        D1 --> DASH[Monitoring Dashboard]
        D2 --> DASH
        D3 --> DASH
    end
    
    style W fill:#4CAF50
    style DASH fill:#2196F3
```

**Monitoring Points**:
- GitHub Actions workflow status
- Azure AI agent execution traces
- Evaluation metric trends
- Red team test results over time

---

## Extension Opportunities

### Future Workflow Enhancements

1. **Multi-Environment Deployment**
```yaml
strategy:
  matrix:
    environment: [dev, test, staging, prod]
    python-version: [3.11, 3.12]
```

2. **Automated PR Testing**
```yaml
on:
  pull_request:
    branches: [main]
```

3. **Scheduled Regression Testing**
```yaml
on:
  schedule:
    - cron: '0 0 * * *'  # Daily at midnight
```

4. **Performance Benchmarking**
```yaml
- name: Run performance tests
  run: python benchmark.py
```

5. **Artifact Publishing**
```yaml
- name: Upload test results
  uses: actions/upload-artifact@v3
  with:
    name: evaluation-results
    path: data_folder/*.json
```

---

## Summary

The GitHub Actions workflow provides:

✅ **Automated Testing**: Validates agent functionality  
✅ **Quality Assurance**: Comprehensive evaluation metrics  
✅ **Security Validation**: Red team adversarial testing  
✅ **Environment Consistency**: Reproducible deployments  
✅ **Audit Trail**: Complete execution logs  
✅ **Secure Authentication**: Azure service principal integration  

This CI/CD pipeline ensures that only thoroughly tested and secure agents are deployed to production environments.
