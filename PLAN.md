# AgentCube Implementation Plan — AR-023 through AR-033

This plan maps Architectural Requirements AR-023 through AR-033 to specific files and implementation details based on the specifications in `./specs/`.

## AR Mapping Overview

| AR | Spec Domain | Package/Path | Description |
|----|-------------|--------------|-------------|
| AR-023 | integrations | `integrations/dify-plugin/` | Dify plugin manifest and provider structure |
| AR-024 | integrations | `integrations/dify-plugin/` | Dify tool schema and implementation |
| AR-025 | example | `example/pcap-analyzer/` | PCAP analyzer FastAPI service |
| AR-026 | deployment | `manifests/charts/base/` | Helm chart templates for Workload Manager |
| AR-027 | deployment | `manifests/charts/base/` | Helm chart templates for Router |
| AR-028 | deployment | `manifests/charts/base/` | Helm chart RBAC and optional Volcano scheduler |
| AR-029 | deployment | `docker/`, `Makefile` | Dockerfiles and build targets |
| AR-030 | ci-cd | `.github/workflows/` | GitHub Actions CI/CD pipelines |
| AR-031 | cli-toolkit | `cmd/cli/agentcube/` | CLI pack/build commands |
| AR-032 | cli-toolkit | `cmd/cli/agentcube/` | CLI publish/invoke/status commands |
| AR-033 | python-sdk | `sdk-python/agentcube/` | SDK clients and exception hierarchy |

---

## AR-023: Dify Plugin Manifest and Provider Structure

### Files to Create

#### 1. `integrations/dify-plugin/main.py`
**Purpose**: Plugin entrypoint that runs the Dify plugin framework.

**Logic**:
- Import `dify_plugin.Plugin` and `dify_plugin.DifyPluginEnv`
- Instantiate `Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))`
- Call `.run()` to start the plugin HTTP server
- Block until the host stops the process

#### 2. `integrations/dify-plugin/manifest.yaml`
**Purpose**: Root plugin manifest for Dify platform registration.

**Structure**:
```yaml
version: 0.0.2
type: plugin
author: volcano-sh
name: agentcube
label:
  en_US: Agentcube
  ja_JP: Agentcube
  zh_Hans: Agentcube
  pt_BR: Agentcube
description:
  en_US: AgentCube integration for Dify
  zh_Hans: AgentCube 集成
icon: icon.png
icon_dark: icon-dark.png
resource:
  memory: 1048576  # 1MB
  permission:
    tool: true
    model: false
    endpoint: false
    app: false
    storage: false
plugins.tools:
  - provider/agentcube.yaml
meta:
  version: 0.0.2
  arch:
    - amd64
    - arm64
  runner:
    language: python
    version: "3.12"
    entrypoint: main
  minimum_dify_version: null
created_at: "2026-03-24T00:00:00Z"
privacy: null
repo: https://github.com/volcano-sh/agentcube
verified: false
```

#### 3. `integrations/dify-plugin/provider/agentcube.yaml`
**Purpose**: Tool provider descriptor that lists tools and points to Python implementation.

**Structure**:
```yaml
identity:
  author: volcano-sh
  name: agentcube
  label:
    en_US: Agentcube Code Interpreter
    zh_Hans: Agentcube 代码解释器
  description:
    en_US: Execute code in AgentCube sandboxes
    zh_Hans: 在 AgentCube 沙箱中执行代码
  icon: icon.png
tools:
  - tools/agentcube-code-interpreter.yaml
extra.python.source: provider/agentcube.py
```

#### 4. `integrations/dify-plugin/provider/agentcube.py`
**Purpose**: Python implementation of the Dify tool provider class.

**Logic**:
- Import `dify_plugin.ToolProvider`
- Import `dify_plugin.errors.tool.ToolProviderCredentialValidationError`
- Define class `AgentcubeCodeInterpreterProvider(ToolProvider)`
- Implement `_validate_credentials(self, credentials: dict[str, Any]) -> None`:
  - Try block: validate that `router_url` and `workload_manager_url` exist in credentials (or implement actual connectivity check)
  - On any exception: raise `ToolProviderCredentialValidationError(str(e))`
- Return without raising on success

#### 5. `integrations/dify-plugin/requirements.txt`
**Purpose**: Pin Python dependencies for reproducible installs.

**Content**:
```
dify-plugin>=0.4.2,<0.5.0
agentcube-sdk>=0.0.10
```

#### 6. `integrations/dify-plugin/.difyignore`
**Purpose**: Specify files to exclude from plugin packaging.

**Content**:
```
__pycache__/
*.pyc
.git/
.env
```

---

## AR-024: Dify Tool Schema and Implementation

### Files to Create

#### 7. `integrations/dify-plugin/tools/agentcube-code-interpreter.yaml`
**Purpose**: Tool parameter schema for Dify configuration UI.

**Structure**:
```yaml
identity:
  name: agentcube-code-interpreter
  author: agentcube
  label:
    human:
      en_US: Code Interpreter
      zh_Hans: 代码解释器
    llm:
      en_US: Execute Python/JavaScript/TypeScript code in a sandbox
  description:
    human:
      en_US: Run code or commands in an AgentCube sandbox
    llm:
      en_US: Use this tool when you need to execute code safely
parameters:
  - name: router_url
    type: string
    required: true
    label:
      en_US: Router URL
    human_description:
      en_US: AgentCube Router endpoint URL
    llm_description: Base URL for the AgentCube Router service
    form: form
  - name: workload_manager_url
    type: string
    required: true
    label:
      en_US: Workload Manager URL
    human_description:
      en_US: AgentCube Workload Manager endpoint URL
    llm_description: Base URL for the Workload Manager control plane
    form: form
  - name: language
    type: select
    required: false
    label:
      en_US: Language
    human_description:
      en_US: Programming language for code execution
    llm_description: One of python, javascript, typescript
    form: llm
    options:
      - value: python
        label:
          en_US: Python
      - value: javascript
        label:
          en_US: JavaScript
      - value: typescript
        label:
          en_US: TypeScript
  - name: code
    type: string
    required: false
    label:
      en_US: Code
    human_description:
      en_US: Code to execute
    llm_description: Source code string
    form: llm
  - name: command
    type: string
    required: false
    label:
      en_US: Command
    human_description:
      en_US: Shell command to execute
    llm_description: Shell command string
    form: llm
  - name: session_id
    type: string
    required: false
    label:
      en_US: Session ID
    human_description:
      en_US: Existing session ID for reuse
    llm_description: Session identifier for stateful execution
    form: llm
  - name: session_reuse
    type: boolean
    required: false
    label:
      en_US: Reuse Session
    human_description:
      en_US: Whether to reuse existing session
    llm_description: Boolean flag for session reuse
    form: llm
  - name: code_interpreter_id
    type: string
    required: false
    label:
      en_US: Code Interpreter ID
    human_description:
      en_US: CodeInterpreter CR name
    llm_description: Name of the CodeInterpreter resource
    form: llm
extra.python.source: tools/agentcube-code-interpreter.py
```

#### 8. `integrations/dify-plugin/tools/agentcube-code-interpreter.py`
**Purpose**: Python tool implementation that delegates to AgentCube SDK.

**Logic**:
- Import `collections.abc.Generator`, `typing.Any`
- Import `dify_plugin.Tool`, `dify_plugin.entities.tool.ToolInvokeMessage`
- Import `agentcube.CodeInterpreterClient`
- Define class `AgentcubeCodeInterpreterTool(Tool)`
- Implement `_invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]`:
  - Call `result = self.execute(**tool_parameters)`
  - Yield `self.create_json_message(result)`
- Implement `execute(self, router_url, workload_manager_url, language="python", code_interpreter_id=None, session_id=None, code=None, command=None, session_reuse=False, **kwargs)`:
  - Validate that at least one of `code` or `command` is provided (raise `ValueError` if neither)
  - Instantiate `CodeInterpreterClient` with:
    - `router_url=router_url`
    - `workload_manager_url=workload_manager_url`
    - `session_id=session_id` if provided
  - Use context manager: `with client:`
    - If `code` is provided: call `client.run_code(code, language=language)`
    - If `command` is provided: call `client.execute_command(command)`
  - Return result dict with `stdout`, `stderr`, `exit_code`, `duration` fields
  - Handle exceptions: on `CommandExecutionError`, return result with error details

#### 9. `integrations/dify-plugin/GUIDE.md`
**Purpose**: Developer guide for installing and testing the Dify plugin.

**Content**:
- Installation steps (pip install requirements)
- Local testing instructions
- Packaging and deployment to Dify
- Configuration requirements (router_url, workload_manager_url)

#### 10. `integrations/dify-plugin/README.md`
**Purpose**: User-facing documentation for the Dify plugin.

**Content**:
- Feature overview
- Usage examples in Dify workflows
- Parameter descriptions
- Troubleshooting guide

---

## AR-025: PCAP Analyzer FastAPI Service

### Files to Create

#### 11. `example/pcap-analyzer/pcap_analyzer.py`
**Purpose**: FastAPI application for PCAP analysis using AgentCube sandboxes.

**Logic**:
- **Imports**:
  - `fastapi.FastAPI`, `UploadFile`, `File`, `Form`, `HTTPException`
  - `pydantic.BaseModel`
  - `uvicorn`
  - `langchain_openai.ChatOpenAI`
  - `langgraph.prebuilt.create_react_agent`
  - `langchain_core.messages.HumanMessage`, `AIMessage`
  - `agentcube.code_interpreter.CodeInterpreterClient`
  - `agentcube.exceptions.CommandExecutionError`
  - `os`, `tempfile`, `shutil`

- **Configuration from environment**:
  - `API_KEY = os.getenv("OPENAI_API_KEY")` (required)
  - `API_BASE_URL = os.getenv("OPENAI_API_BASE", "https://api.siliconflow.cn/v1")`
  - `MODEL_NAME = os.getenv("OPENAI_MODEL", "Qwen/QwQ-32B")`
  - `CODEINTERPRETER_NAME = os.getenv("CODEINTERPRETER_NAME", "my-interpreter")`
  - `SANDBOX_NAMESPACE = os.getenv("SANDBOX_NAMESPACE", "default")`
  - `SANDBOX_WARMUP_SEC = int(os.getenv("SANDBOX_WARMUP_SEC", "5"))`
  - `SERVER_HOST = "0.0.0.0"`, `SERVER_PORT = 8000`, `SERVER_RELOAD = True`

- **Define `SandboxRunner` class**:
  - `__init__(self, name, namespace, warmup_sec)`: store config, create `CodeInterpreterClient` later
  - `upload_file(self, local_path, remote_path) -> bool`: use client to upload file
  - `upload_bytes(self, data, remote_path) -> bool`: encode to base64, use client write
  - `run(self, command) -> dict[str, Any]`: execute command via client, return result
  - `stop(self)`: close client connection

- **Define agent builders**:
  - `build_react_agent(llm, system_prompt)`: create ReAct agent with LangGraph
  - `invoke_react_agent(agent, user_text) -> str`: run agent and extract response text
  - `build_planner_agent(llm)`: build agent that plans PCAP analysis scripts
  - `build_reporter_agent(llm)`: build agent that generates final reports

- **Define orchestration functions**:
  - `_plan_script(agent, pcap_local_path) -> str`: generate analysis plan
  - `_repair_script(agent, prev_script, results) -> str`: repair failed script
  - `_execute_once_in_runner(runner, pcap_local_path, script) -> list[dict]`: execute script steps
  - `_analyze_with_retries(..., max_retries=2) -> dict`: orchestrate plan/execute/repair loop
  - `_report(agent, results) -> str`: generate summary report

- **Define `AnalyzeResponse` Pydantic model**:
  - `script: str`
  - `results: list[dict[str, Any]]`
  - `report: str`

- **Create FastAPI app**:
  - `app = FastAPI(title="PCAP Analyzer")`

- **Startup event**:
  - `@app.on_event("startup")`:
    - Validate `API_KEY` is set, fail if missing
    - Build `ChatOpenAI(api_key=API_KEY, base_url=API_BASE_URL, model=MODEL_NAME)`
    - Initialize `PLANNER = build_planner_agent(llm)`
    - Initialize `REPORTER = build_reporter_agent(llm)`

- **POST `/analyze` endpoint**:
  - Accept `pcap_file: UploadFile = File(None)` and `pcap_path: str = Form(None)`
  - Validate at least one of `pcap_file` or `pcap_path` is provided
  - If `pcap_file`: save to temp file
  - Create `SandboxRunner` with config
  - Try block:
    - Call `_analyze_with_retries(...)`
    - Call `_report(...)`
    - Return `AnalyzeResponse(script=..., results=..., report=...)`
  - Finally: call `runner.stop()`
  - Handle exceptions: return `HTTPException(500, str(e))`

- **Main block**:
  - `uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, reload=SERVER_RELOAD)`

#### 12. `example/pcap-analyzer/requirements.txt`
**Purpose**: Python dependencies for PCAP analyzer.

**Content**:
```
fastapi==0.120.0
uvicorn==0.38.0
python-multipart==0.0.20
langchain==1.0.2
langchain-classic==1.0.0
langchain-community==0.4.1
langchain-core==1.0.1
langchain-openai==1.0.1
langchain-text-splitters==1.0.0
langgraph==1.0.1
langgraph-checkpoint==3.0.0
langgraph-prebuilt==1.0.1
langgraph-sdk==0.2.9
langsmith==0.4.38
paramiko==4.0.0
```

#### 13. `example/pcap-analyzer/Dockerfile`
**Purpose**: Container image for PCAP analyzer deployment.

**Content**:
```dockerfile
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install uv and dependencies
RUN uv venv
COPY requirements.txt .
RUN uv pip install -r requirements.txt

# Vendor agentcube SDK from monorepo
COPY sdk-python/agentcube ./agentcube/

# Copy application
COPY pcap_analyzer.py ./

ENV PYTHONPATH="/app"
EXPOSE 8000

CMD ["uv", "run", "pcap_analyzer.py"]
```

#### 14. `example/pcap-analyzer/deployment.yaml`
**Purpose**: Kubernetes Deployment for PCAP analyzer.

**Content**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: pcap-analyzer
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: pcap-analyzer
  template:
    metadata:
      labels:
        app: pcap-analyzer
    spec:
      containers:
        - name: pcap-analyzer
          image: pcap-analyzer:latest
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
          resources:
            requests:
              cpu: 200m
              memory: 100Mi
            limits:
              cpu: "1"
              memory: 1Gi
          env:
            - name: OPENAI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: pcap-analyzer-secrets
                  key: openai-api-key
            - name: OPENAI_API_BASE
              value: "https://api.siliconflow.cn/v1"
            - name: OPENAI_MODEL
              value: "Qwen/QwQ-32B"
            - name: WORKLOAD_MANAGER_URL
              value: "http://workloadmanager.default.svc.cluster.local:8080"
            - name: ROUTER_URL
              value: "http://agentcube-router.default.svc.cluster.local:8080"
            - name: CODEINTERPRETER_NAME
              value: "my-interpreter"
            - name: SANDBOX_NAMESPACE
              value: "default"
            - name: SANDBOX_WARMUP_SEC
              value: "5"
          command: ["uv"]
          args: ["run", "pcap_analyzer.py"]
```

#### 15. `example/pcap-analyzer/README.md`
**Purpose**: Documentation for PCAP analyzer usage and deployment.

**Content**:
- Overview of PCAP analysis capabilities
- Local development instructions
- Kubernetes deployment guide
- API endpoint documentation
- Environment variable reference

---

## AR-026: Helm Chart — Workload Manager Templates

### Files to Create

#### 16. `manifests/charts/base/Chart.yaml`
**Purpose**: Helm chart metadata.

**Content**:
```yaml
apiVersion: v2
name: agentcube
description: AgentCube sandbox orchestration platform
type: application
version: 0.1.0
appVersion: "0.1.0"
keywords:
  - agent
  - sandbox
  - kubernetes
maintainers:
  - name: volcano-sh
home: https://github.com/volcano-sh/agentcube
```

#### 17. `manifests/charts/base/values.yaml`
**Purpose**: Default configuration values for the chart.

**Content**:
```yaml
# Global settings
namespace: default

# Redis configuration (required)
redis:
  addr: ""  # e.g., "redis-master:6379"
  password: ""

# Workload Manager configuration
workloadmanager:
  replicas: 1
  image:
    repository: agentcube/workloadmanager
    tag: latest
    pullPolicy: IfNotPresent
  service:
    type: ClusterIP
    port: 8080
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
  healthCheck:
    liveness:
      path: /health
      initialDelaySeconds: 10
      periodSeconds: 10
    readiness:
      path: /health
      initialDelaySeconds: 5
      periodSeconds: 5
  extraEnv: []

# Router configuration
router:
  replicas: 1
  image:
    repository: agentcube/router
    tag: latest
    pullPolicy: IfNotPresent
  service:
    type: ClusterIP
    port: 8080
    targetPort: 8080
  resources:
    requests:
      cpu: 100m
      memory: 256Mi
    limits:
      cpu: 500m
      memory: 512Mi
  serviceAccountName: ""
  debug: true
  rbac:
    create: false

# Optional Volcano scheduler
volcano:
  scheduler:
    enabled: false
    image:
      repository: volcano-sh/volcano-agent-scheduler
      tag: latest

# CRDs
crds:
  create: true
```

#### 18. `manifests/charts/base/templates/workloadmanager-deployment.yaml`
**Purpose**: Workload Manager Deployment manifest.

**Logic**:
- Name: `workloadmanager`
- Replicas from `.Values.workloadmanager.replicas`
- Image from `.Values.workloadmanager.image`
- Container ports: 8080
- Environment variables:
  - `REDIS_ADDR` from `.Values.redis.addr`
  - `REDIS_PASSWORD` from `.Values.redis.password`
  - Extra env from `.Values.workloadmanager.extraEnv`
- Liveness probe: HTTP GET `.Values.workloadmanager.healthCheck.liveness.path`
- Readiness probe: HTTP GET `.Values.workloadmanager.healthCheck.readiness.path`
- Resources from `.Values.workloadmanager.resources`
- ServiceAccount: `workloadmanager`

#### 19. `manifests/charts/base/templates/workloadmanager-service.yaml`
**Purpose**: Workload Manager Service manifest.

**Logic**:
- Name: `workloadmanager`
- Type from `.Values.workloadmanager.service.type`
- Port from `.Values.workloadmanager.service.port`
- Target port: 8080
- Selector: `app: workloadmanager`

#### 20. `manifests/charts/base/templates/workloadmanager-serviceaccount.yaml`
**Purpose**: Workload Manager ServiceAccount.

**Logic**:
- Name: `workloadmanager`
- Namespace: release namespace

#### 21. `manifests/charts/base/templates/rbac/workloadmanager-clusterrole.yaml`
**Purpose**: Workload Manager ClusterRole with required permissions.

**Logic**:
- Name: `workloadmanager`
- Rules:
  - API group `agents.x-k8s.io`: sandboxes (get, list, watch, create, update, patch, delete)
  - API group `extensions.agents.x-k8s.io`: sandboxclaims (get, list, watch, create, update, patch, delete)
  - API group `runtime.agentcube.volcano.sh`: agentruntimes, codeinterpreters (get, list, watch, create, update, patch, delete)
  - API group `` (core): pods (get, list, watch), secrets (get, list, watch)
  - API group `authentication.k8s.io`: tokenreviews (create)

#### 22. `manifests/charts/base/templates/rbac/workloadmanager-clusterrolebinding.yaml`
**Purpose**: Bind Workload Manager ServiceAccount to ClusterRole.

**Logic**:
- Name: `workloadmanager`
- RoleRef: `ClusterRole/workloadmanager`
- Subjects: `ServiceAccount/workloadmanager` in release namespace

---

## AR-027: Helm Chart — Router Templates

### Files to Create

#### 23. `manifests/charts/base/templates/router-deployment.yaml`
**Purpose**: Router Deployment manifest.

**Logic**:
- Name: `agentcube-router`
- Replicas from `.Values.router.replicas`
- Image from `.Values.router.image`
- Container args: `--port={{ .Values.router.service.targetPort }}`, `--debug` (if enabled)
- Environment variables:
  - `REDIS_ADDR` from `.Values.redis.addr`
  - `REDIS_PASSWORD` from `.Values.redis.password`
  - `WORKLOAD_MANAGER_URL` = `http://workloadmanager.{{ .Release.Namespace }}.svc.cluster.local:{{ .Values.workloadmanager.service.port }}`
- ServiceAccount: from `.Values.router.serviceAccountName` or `agentcube-router`
- Resources from `.Values.router.resources`

#### 24. `manifests/charts/base/templates/router-service.yaml`
**Purpose**: Router Service manifest.

**Logic**:
- Name: `agentcube-router`
- Type: ClusterIP
- Port from `.Values.router.service.port`
- Target port from `.Values.router.service.targetPort`
- Selector: `app: agentcube-router`

#### 25. `manifests/charts/base/templates/router/rbac-serviceaccount.yaml`
**Purpose**: Optional Router ServiceAccount (when RBAC enabled).

**Logic**:
- Conditional: `.Values.router.rbac.create`
- Name: from `.Values.router.serviceAccountName` or `agentcube-router`

#### 26. `manifests/charts/base/templates/router/rbac-role.yaml`
**Purpose**: Optional Router Role for secret management.

**Logic**:
- Conditional: `.Values.router.rbac.create`
- Name: `agentcube-router`
- Namespace: release namespace
- Rules: secrets (get, list, watch, create, update, patch, delete)

#### 27. `manifests/charts/base/templates/router/rbac-rolebinding.yaml`
**Purpose**: Bind Router ServiceAccount to Role.

**Logic**:
- Conditional: `.Values.router.rbac.create`
- Name: `agentcube-router`
- RoleRef: `Role/agentcube-router`
- Subjects: ServiceAccount in release namespace

---

## AR-028: Helm Chart — CRDs and Optional Volcano Scheduler

### Files to Create

#### 28. `manifests/charts/base/crds/agentruntime-crd.yaml`
**Purpose**: AgentRuntime CRD definition.

**Content**:
- API group: `runtime.agentcube.volcano.sh`
- Version: `v1alpha1`
- Kind: `AgentRuntime`
- Scope: `Namespaced`
- Subresources: `status`
- AdditionalPrinterColumns: Age from `.metadata.creationTimestamp`
- Spec schema: `Ports`, `Template` (SandboxTemplate), `SessionTimeout`, `MaxSessionDuration`

#### 29. `manifests/charts/base/crds/codeinterpreter-crd.yaml`
**Purpose**: CodeInterpreter CRD definition.

**Content**:
- API group: `runtime.agentcube.volcano.sh`
- Version: `v1alpha1`
- Kind: `CodeInterpreter`
- Scope: `Namespaced`
- Subresources: `status`
- AdditionalPrinterColumns: Age from `.metadata.creationTimestamp`
- Spec schema: `Ports`, `Template`, `SessionTimeout`, `MaxSessionDuration`, `WarmPoolSize`, `AuthMode`

#### 30. `manifests/charts/base/templates/volcano/scheduler-serviceaccount.yaml`
**Purpose**: Volcano scheduler ServiceAccount.

**Logic**:
- Conditional: `.Values.volcano.scheduler.enabled`
- Name: `volcano-agent-scheduler`

#### 31. `manifests/charts/base/templates/volcano/scheduler-configmap.yaml`
**Purpose**: Volcano scheduler ConfigMap.

**Logic**:
- Conditional: `.Values.volcano.scheduler.enabled`
- Configuration for Volcano agent scheduler

#### 32. `manifests/charts/base/templates/volcano/scheduler-clusterrole.yaml`
**Purpose**: Volcano scheduler ClusterRole.

**Logic**:
- Conditional: `.Values.volcano.scheduler.enabled`
- Permissions for pod scheduling

#### 33. `manifests/charts/base/templates/volcano/scheduler-clusterrolebinding.yaml`
**Purpose**: Bind Volcano scheduler to ClusterRole.

**Logic**:
- Conditional: `.Values.volcano.scheduler.enabled`

#### 34. `manifests/charts/base/templates/volcano/scheduler-service.yaml`
**Purpose**: Volcano scheduler Service.

**Logic**:
- Conditional: `.Values.volcano.scheduler.enabled`

#### 35. `manifests/charts/base/templates/volcano/scheduler-deployment.yaml`
**Purpose**: Volcano scheduler Deployment.

**Logic**:
- Conditional: `.Values.volcano.scheduler.enabled`
- Image from `.Values.volcano.scheduler.image`

---

## AR-029: Dockerfiles and Makefile Build Targets

### Files to Create/Modify

#### 36. `docker/Dockerfile` (Workload Manager)
**Purpose**: Multi-stage build for Workload Manager binary.

**Content**:
```dockerfile
# Build stage
FROM golang:1.24-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /workloadmanager ./cmd/workload-manager

# Runtime stage
FROM alpine:3.19
RUN adduser -D -u 1000 apiserver
COPY --from=builder /workloadmanager /workloadmanager
USER apiserver
EXPOSE 8080
ENTRYPOINT ["/workloadmanager"]
```

#### 37. `docker/Dockerfile.router` (Router)
**Purpose**: Multi-stage build for Router binary.

**Content**:
```dockerfile
# Build stage
FROM golang:1.24-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /router ./cmd/router

# Runtime stage
FROM alpine:3.19
RUN adduser -D -u 1000 router
COPY --from=builder /router /router
USER router
EXPOSE 8080
ENTRYPOINT ["/router"]
```

#### 38. `docker/Dockerfile.picod` (PicoD)
**Purpose**: Multi-stage build for PicoD binary.

**Content**:
```dockerfile
# Build stage
FROM golang:1.24-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /picod ./cmd/picod

# Runtime stage
FROM alpine:3.19
RUN adduser -D -u 1000 picod
COPY --from=builder /picod /picod
USER picod
EXPOSE 8080
ENTRYPOINT ["/picod"]
```

#### 39. `Makefile` (modify existing)
**Purpose**: Build automation targets.

**Targets to add/modify**:
- `all`: default → `build`
- `build`: generate → `bin/workloadmanager` from `./cmd/workload-manager`
- `build-router`: `bin/router` from `./cmd/router`
- `build-picod`: `bin/picod` from `./cmd/picod`
- `test`: run Go tests with coverage
- `docker-build`: build all Docker images
- `docker-push`: push images to registry
- `docker-workloadmanager`: build workload manager image
- `docker-router`: build router image
- `docker-picod`: build picod image
- `generate`: run code generation
- `gen-crd`: generate CRD manifests
- `gen-client`: generate client-go code
- `gen-all`: `generate` + `gen-crd` + `gen-client`
- `gen-check`: verify generated files are up to date
- `e2e`: run `./test/e2e/run_e2e.sh`
- `e2e-clean`: clean up E2E test resources
- `helm-lint`: lint Helm chart
- `helm-template`: render Helm templates
- `install`: deploy to cluster using Helm

---

## AR-030: GitHub Actions CI/CD Pipelines

### Files to Create

#### 40. `.github/workflows/ci.yaml`
**Purpose**: Continuous integration workflow.

**Logic**:
- Triggers: push to main, PRs to main
- Jobs:
  - `lint`: run `golangci-lint`, Python linting
  - `test`: run Go tests with coverage
  - `build`: build all binaries
  - `helm-lint`: validate Helm chart
  - `gen-check`: verify generated code is up to date

#### 41. `.github/workflows/cd.yaml`
**Purpose**: Continuous deployment workflow.

**Logic**:
- Triggers: tags matching `v*.*.*`
- Jobs:
  - `build-images`: build and push Docker images to registry
  - `helm-release`: package and release Helm chart
  - `publish-sdk`: publish Python SDK to PyPI

#### 42. `.github/workflows/e2e.yaml`
**Purpose**: E2E test workflow.

**Logic**:
- Triggers: push to main, PRs to main
- Jobs:
  - `e2e-tests`:
    - Set up Kind cluster
    - Deploy dependencies (Redis, Volcano)
    - Install Helm chart
    - Run Go E2E tests
    - Run Python SDK E2E tests
    - Upload test artifacts

---

## AR-031: CLI Toolkit — Pack and Build Commands

### Files to Create

#### 43. `cmd/cli/pyproject.toml`
**Purpose**: Python CLI project metadata and dependencies.

**Content**:
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "kubectl-agentcube"
version = "0.1.0"
description = "AgentCube CLI for packaging and deploying AI agents"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.9.0",
    "rich>=13.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "docker>=7.0.0",
    "kubernetes>=28.0.0",
    "requests>=2.31.0",
]

[project.scripts]
agentcube = "agentcube.cli.main:app"
```

#### 44. `cmd/cli/agentcube/__init__.py`
**Purpose**: Package initialization with version constant.

**Content**:
```python
__version__ = "0.1.0"
__all__ = ["__version__"]
```

#### 45. `cmd/cli/agentcube/cli/main.py`
**Purpose**: Typer CLI application with subcommands.

**Logic**:
- Import `typer`, `logging`, `rich`
- Define root callback with:
  - `--version` (eager, Optional[bool]): print version and exit
  - `--verbose` / `-v` (bool): enable debug logging
- Create `app = typer.Typer()`
- Register subcommands: `pack`, `build`, `publish`, `invoke`, `status`
- Implement error handler `_handle_error(e, command_name, verbose)`:
  - Print error message in red
  - If verbose: print traceback
  - Raise `typer.Exit(1)`

#### 46. `cmd/cli/agentcube/models/pack_models.py`
**Purpose**: Pydantic models for metadata validation.

**Logic**:
- Define `AgentMetadata` Pydantic model:
  - `agent_name: str`
  - `language: str` (validator: must be `python`, `java`, etc.)
  - `entrypoint: str`
  - `port: int` (validator: 1-65535)
  - `build_mode: str` (validator: `local`, `cloud`)
  - `version: str`
  - `description: str`
  - `router_url: str | None`
  - `workload_manager_url: str | None`
  - `agent_id: str | None`
  - `session_id: str | None`
  - `status: str | None`

#### 47. `cmd/cli/agentcube/services/metadata_service.py`
**Purpose**: Load and save agent metadata YAML.

**Logic**:
- Class `MetadataService`:
  - `load_metadata(workspace_path) -> AgentMetadata`:
    - Try `agent_metadata.yaml`, fall back to `agent.yaml`, then `metadata.yaml`
    - Parse YAML, validate with Pydantic
  - `save_metadata(metadata, workspace_path)`:
    - Write to `{workspace}/agent_metadata.yaml`
    - Use `yaml.dump` with proper formatting
  - `update_metadata(metadata, updates)`: merge changes

#### 48. `cmd/cli/agentcube/services/docker_service.py`
**Purpose**: Docker SDK wrapper for image operations.

**Logic**:
- Class `DockerService`:
  - `check_docker_available()`: raise `RuntimeError` if Docker unavailable
  - `build_image(workspace_path, image_name, tag, buildargs=None) -> dict`:
    - Use `docker.from_env()`
    - Call `docker.images.build()`
    - Return `image_name`, `image_id`, `image_size`, `build_time`
  - `push_image(image_name, registry_url=None, username=None, password=None) -> dict`:
    - Login if credentials provided
    - Retag if needed
    - Stream push logs
    - Return `pushed_image`, `push_time`
  - `remove_image(image_name) -> bool`: remove and handle errors

#### 49. `cmd/cli/agentcube/services/k8s_provider.py`
**Purpose**: Standard Kubernetes deployment provider.

**Logic**:
- Class `KubernetesProvider`:
  - `__init__()`: initialize Kubernetes client
  - `deploy_agent(config) -> dict`:
    - Create/patch Deployment
    - Create/patch NodePort Service
    - Return deployment info
  - `wait_for_deployment_ready(deployment_name, namespace, timeout=120)`:
    - Poll deployment status
    - Raise `TimeoutError` on timeout
  - `delete_agent(deployment_name, namespace) -> dict`:
    - Delete Deployment and Service
    - Ignore 404 errors
  - `get_agent_status(deployment_name, namespace) -> dict`:
    - Return pod status

#### 50. `cmd/cli/agentcube/services/agentcube_provider.py`
**Purpose**: AgentCube CRD provider.

**Logic**:
- Class `AgentCubeProvider`:
  - `__init__()`: initialize Kubernetes client with custom API
  - `deploy_agent_runtime(config) -> dict`:
    - Build AgentRuntime CR object
    - Create/patch via CustomObjects API
    - Set env vars: `WORKLOAD_MANAGER_URL`, `ROUTER_URL`
    - Set `sessionTimeout: "15m"`, `maxSessionDuration: "8h"`
  - `get_agent_runtime_status(name, namespace) -> dict`:
    - Get CR from API
    - Extract status from `.status`
  - `delete_agent_runtime(name, namespace) -> dict`:
    - Delete CR, ignore 404

#### 51. `cmd/cli/agentcube/runtime/pack_runtime.py`
**Purpose**: Pack command implementation.

**Logic**:
- Class `PackRuntime`:
  - `__init__(metadata_overrides)`: store overrides
  - `pack(workspace_path) -> tuple[str, str]`:
    - Validate workspace exists and is directory
    - Validate language-specific requirements (Python: *.py files, Java: pom.xml)
    - Load or create metadata
    - Merge CLI overrides
    - Optionally generate Dockerfile
    - Save metadata
    - Return `(agent_name, metadata_path)`

#### 52. `cmd/cli/agentcube/runtime/build_runtime.py`
**Purpose**: Build command implementation.

**Logic**:
- Class `BuildRuntime`:
  - `__init__(proxy=None, cloud_provider=None)`: store config
  - `build(workspace_path) -> dict`:
    - Load metadata
    - Increment version (patch bump)
    - Check Docker availability for local build
    - Call `DockerService.build_image()`
    - Update metadata with image info
    - On failure: revert version
    - Return build result

---

## AR-032: CLI Toolkit — Publish, Invoke, Status Commands

### Files to Create

#### 53. `cmd/cli/agentcube/runtime/publish_runtime.py`
**Purpose**: Publish command implementation.

**Logic**:
- Class `PublishRuntime`:
  - `__init__(provider, version=None, image_url=None, ...)`: store config
  - `publish(workspace_path) -> dict`:
    - Load metadata
    - If provider `agentcube`:
      - Validate `router_url` and `workload_manager_url` present
      - Use `AgentCubeProvider.deploy_agent_runtime()`
    - If provider `k8s`:
      - Use `KubernetesProvider.deploy_agent()`
      - Wait for deployment ready
    - Update metadata with deployment info
    - Return publish result

#### 54. `cmd/cli/agentcube/runtime/invoke_runtime.py`
**Purpose**: Invoke command implementation.

**Logic**:
- Class `InvokeRuntime`:
  - `__init__(provider, headers=None)`: store config
  - `invoke(workspace_path, payload) -> dict`:
    - Load metadata
    - Build target URL:
      - If AgentRuntime CR: `{base}/v1/namespaces/{ns}/agent-runtimes/{name}/invocations/`
      - Else: from metadata
    - Add headers:
      - `X-Agentcube-Session-Id` if session_id in metadata
      - Custom headers from CLI
    - POST JSON payload
    - Return response

#### 55. `cmd/cli/agentcube/runtime/status_runtime.py`
**Purpose**: Status command implementation.

**Logic**:
- Class `StatusRuntime`:
  - `__init__(provider)`: store config
  - `get_status(workspace_path) -> dict`:
    - Load metadata
    - If no `agent_id`: return `status=not_published`
    - If provider `agentcube`:
      - Call `AgentCubeProvider.get_agent_runtime_status()`
    - If provider `k8s`:
      - Call `KubernetesProvider.get_agent_status()`
    - Return status dict

#### 56. `cmd/cli/agentcube/cli/pack.py`
**Purpose**: Pack subcommand definition.

**Logic**:
- Define `@app.command("pack")`:
  - Options: `workspace`, `agent_name`, `language`, `entrypoint`, `port`, `build_mode`, `description`, `output`, `verbose`
  - Use `Progress` spinner
  - Call `PackRuntime.pack()`
  - Print success or handle error

#### 57. `cmd/cli/agentcube/cli/build.py`
**Purpose**: Build subcommand definition.

**Logic**:
- Define `@app.command("build")`:
  - Options: `workspace`, `proxy`, `cloud_provider`, `output`, `verbose`
  - Call `BuildRuntime.build()`
  - Print build result
  - Handle errors

#### 58. `cmd/cli/agentcube/cli/publish.py`
**Purpose**: Publish subcommand definition.

**Logic**:
- Define `@app.command("publish")`:
  - Options: `workspace`, `version`, `image_url`, `image_username`, `image_password`, `description`, `region`, `cloud_provider`, `provider`, `node_port`, `replicas`, `namespace`, `verbose`
  - Call `PublishRuntime.publish()`
  - Print deployment info

#### 59. `cmd/cli/agentcube/cli/invoke.py`
**Purpose**: Invoke subcommand definition.

**Logic**:
- Define `@app.command("invoke")`:
  - Options: `workspace`, `payload`, `header` (repeatable), `provider`, `verbose`
  - Parse payload as JSON (exit 1 if invalid)
  - Parse headers as `key:value` (exit 1 if invalid format)
  - Call `InvokeRuntime.invoke()`
  - Print response

#### 60. `cmd/cli/agentcube/cli/status.py`
**Purpose**: Status subcommand definition.

**Logic**:
- Define `@app.command("status")`:
  - Options: `workspace`, `provider`, `verbose`
  - Call `StatusRuntime.get_status()`
  - Display Rich Table with status info
  - Exit 1 if `not_published` or `error`

---

## AR-033: Python SDK — Clients and Exceptions

### Files to Create

#### 61. `sdk-python/pyproject.toml`
**Purpose**: Python SDK project metadata.

**Content**:
```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agentcube-sdk"
version = "0.0.10"
description = "Python SDK for AgentCube sandbox orchestration"
requires-python = ">=3.10"
dependencies = [
    "requests>=2.31.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
]
```

#### 62. `sdk-python/agentcube/__init__.py`
**Purpose**: Package initialization with public API exports.

**Content**:
```python
from agentcube.code_interpreter import CodeInterpreterClient
from agentcube.agent_runtime import AgentRuntimeClient

__all__ = ["CodeInterpreterClient", "AgentRuntimeClient"]
```

#### 63. `sdk-python/agentcube/exceptions.py`
**Purpose**: Exception hierarchy for SDK errors.

**Logic**:
- Define `AgentCubeError(Exception)`: base exception
- Define `CommandExecutionError(AgentCubeError)`:
  - Constructor: `exit_code`, `stderr`, `command`
  - Store as instance attributes
- Define `SessionError(AgentCubeError)`: session-related errors
- Define `DataPlaneError(AgentCubeError)`: data plane errors

#### 64. `sdk-python/agentcube/clients/control_plane.py`
**Purpose**: Workload Manager HTTP client.

**Logic**:
- Class `ControlPlaneClient`:
  - `__init__(workload_manager_url, auth_token=None)`:
    - Resolve URL from arg or `WORKLOAD_MANAGER_URL` env
    - Resolve token from arg or `/var/run/secrets/kubernetes.io/serviceaccount/token`
    - Create `requests.Session` with connection pooling
    - Set `Authorization: Bearer {token}` if present
  - `create_session(name, namespace, metadata=None, ttl=3600) -> str`:
    - POST to `/v1/code-interpreter`
    - JSON: `{name, namespace, ttl, metadata}`
    - Return `data["sessionId"]` or raise `ValueError`
  - `delete_session(session_id) -> bool`:
    - DELETE to `/v1/code-interpreter/sessions/{session_id}`
    - Return True on 404 or success, False on other errors

#### 65. `sdk-python/agentcube/clients/code_interpreter_data_plane.py`
**Purpose**: Router data plane client for Code Interpreter.

**Logic**:
- Class `CodeInterpreterDataPlaneClient`:
  - `__init__(router_url, namespace, cr_name, session_id, timeout=120, connect_timeout=5.0)`:
    - Build base URL using `urljoin`
    - Create `requests.Session`
    - Set default header `x-agentcube-session-id: {session_id}`
  - `_request(method, path, **kwargs)`:
    - Add timeout tuple: `(connect_timeout, read_timeout)`
    - Raise on HTTP errors
  - `execute_command(command, timeout=None) -> dict`:
    - POST to `api/execute`
    - JSON: `{command: [...], timeout: "<n>s"}`
    - If `exit_code != 0`: raise `CommandExecutionError`
  - `write_file(path, content, mode="0644")`:
    - POST to `api/files` with base64 content
  - `upload_file(local_path, remote_path)`:
    - Multipart POST to `api/files`
  - `download_file(remote_path, local_path)`:
    - GET from `api/files/{path}`, stream to file
  - `list_files(path) -> list`:
    - GET from `api/files?path={path}`

#### 66. `sdk-python/agentcube/clients/agent_runtime_data_plane.py`
**Purpose**: Router data plane client for Agent Runtime.

**Logic**:
- Class `AgentRuntimeDataPlaneClient`:
  - `SESSION_HEADER = "x-agentcube-session-id"`
  - `__init__(router_url, namespace, agent_name, session_id, timeout=120, connect_timeout=5.0)`:
    - Build invocation base URL
    - Create `requests.Session`
  - `_request(method, path, **kwargs)`:
    - Add timeout tuple
  - `invoke(payload, timeout=None) -> dict`:
    - POST JSON to invocation URL
    - Set `SESSION_HEADER` and `Content-Type`

#### 67. `sdk-python/agentcube/code_interpreter.py`
**Purpose**: High-level Code Interpreter client.

**Logic**:
- Class `CodeInterpreterClient`:
  - `__init__(router_url, workload_manager_url=None, name=None, namespace="default", session_id=None, ttl=3600, timeout=120)`:
    - Validate `router_url` is provided (arg or `ROUTER_URL` env)
    - Store config
    - If `session_id` not provided:
      - Create `ControlPlaneClient`
      - Call `create_session()`
      - Handle failure: delete session, re-raise
    - Call `_init_data_plane()`
  - `_init_data_plane()`:
    - Create `CodeInterpreterDataPlaneClient` with session_id
  - `__enter__()`: return self
  - `__exit__(exc_type, exc_val, exc_tb)`: call `stop()`
  - `stop()`:
    - Close data plane session
    - If created session: call `delete_session()`
    - Close control plane session
  - `execute_command(command, timeout=None) -> dict`: delegate to data plane
  - `run_code(code, language="python") -> dict`:
    - Write timestamped `.py` file
    - Execute `python3 <file>`
  - `write_file(path, content)`: delegate
  - `upload_file(local_path, remote_path)`: delegate
  - `download_file(remote_path, local_path)`: delegate
  - `list_files(path) -> list`: delegate

#### 68. `sdk-python/agentcube/agent_runtime.py`
**Purpose**: High-level Agent Runtime client.

**Logic**:
- Class `AgentRuntimeClient`:
  - `__init__(router_url, namespace, agent_name, session_id=None, timeout=120, connect_timeout=5.0)`:
    - Store config
    - If `session_id` not provided:
      - GET from invocation base URL
      - Read `x-agentcube-session-id` from response header
      - Raise `ValueError` if missing
    - Create `AgentRuntimeDataPlaneClient`
  - `__enter__()`: return self
  - `__exit__(exc_type, exc_val, exc_tb)`: call `close()`
  - `close()`: close underlying session
  - `invoke(payload, timeout=None) -> dict`:
    - If no session_id: raise `ValueError`
    - Delegate to data plane

#### 69. `sdk-python/agentcube/utils/http.py`
**Purpose**: HTTP utility functions.

**Logic**:
- `read_token_from_file(path) -> str | None`:
  - Read file, return stripped contents
  - Handle FileNotFoundError, return None
- `create_session(timeout=120, connect_timeout=5.0) -> tuple`:
  - Create `requests.Session`
  - Mount `HTTPAdapter` with pool settings
  - Return session and timeout tuple

#### 70. `sdk-python/agentcube/utils/utils.py`
**Purpose**: General utility functions.

**Logic**:
- `ensure_dir(path)`: create directory if not exists
- `generate_timestamp() -> str`: ISO format timestamp
- `base64_encode(data) -> str`: standard base64 encoding
- `base64_decode(s) -> bytes`: standard base64 decoding

#### 71. `sdk-python/agentcube/utils/log.py`
**Purpose**: Logging configuration.

**Logic**:
- `setup_logging(level=logging.INFO)`:
  - Configure root logger with format
  - Return logger instance

---

## File Summary

| File Count | Category |
|------------|----------|
| 10 | AR-023: Dify Plugin Manifest |
| 8 | AR-024: Dify Tool Schema |
| 5 | AR-025: PCAP Analyzer |
| 6 | AR-026: Helm Workload Manager |
| 5 | AR-027: Helm Router |
| 8 | AR-028: Helm CRDs & Volcano |
| 4 | AR-029: Dockerfiles & Makefile |
| 3 | AR-030: GitHub Actions |
| 10 | AR-031: CLI Pack/Build |
| 8 | AR-032: CLI Publish/Invoke/Status |
| 11 | AR-033: Python SDK |
| **Total: 78 files** |

---

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
1. **Python SDK (AR-033)**: Create core SDK clients and exceptions
2. **Helm Chart Base (AR-026, AR-027, AR-028)**: Set up chart structure, CRDs, and base templates
3. **Dockerfiles (AR-029)**: Create multi-stage builds for all Go binaries

### Phase 2: Integrations (Week 2-3)
1. **Dify Plugin (AR-023, AR-024)**: Implement plugin manifest, provider, and tool schemas
2. **CLI Toolkit (AR-031, AR-032)**: Build CLI commands for pack, build, publish, invoke, status

### Phase 3: Examples and CI/CD (Week 3-4)
1. **PCAP Analyzer (AR-025)**: Create example FastAPI service
2. **CI/CD Pipelines (AR-030)**: Set up GitHub Actions workflows

### Phase 4: Testing and Polish (Week 4-5)
1. **Integration Tests**: End-to-end tests for all components
2. **Documentation**: README files and guides
3. **Performance Optimization**: Optimize bottlenecks

---

## Dependencies and Prerequisites

### External Dependencies
- Go 1.24+ for control plane components
- Python 3.10+ for SDK, CLI, and integrations
- Kubernetes 1.28+ cluster with CRD support
- Helm 3.x for chart installation
- Docker with Buildx for multi-arch images
- Redis 6+ for session storage

### Internal Dependencies
- SDK must be built before CLI and Dify plugin
- CRDs must exist before deploying Workload Manager/Router
- Helm chart must be complete before CI/CD pipelines

---

## Risk Mitigation

### High Priority Risks
1. **Dify Plugin Compatibility**: Test against latest Dify version early
2. **Kubernetes RBAC**: Verify ClusterRole permissions match actual usage
3. **Session Management**: Ensure proper cleanup in SDK context managers

### Mitigation Strategies
- Implement comprehensive error handling in all clients
- Use connection pooling and timeouts for HTTP clients
- Add health checks and monitoring endpoints
- Create rollback procedures for deployments
