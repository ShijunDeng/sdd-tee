# Integrations Specification

## Purpose

Normative requirements for the AgentCube Dify plugin integration and the PCAP analyzer example that uses AgentCube code interpreters and Kubernetes sandboxes.

## Requirements

### Requirement: Dify plugin bootstrap and runtime

The system SHALL expose a Dify-compatible Python plugin whose process entry runs the framework runner with a configured maximum request timeout.

#### Scenario: Plugin process starts

- **GIVEN** the plugin package is installed with compatible `dify-plugin` and `agentcube-sdk` versions
- **WHEN** the platform starts the plugin using the manifest-declared entrypoint
- **THEN** the plugin SHALL execute `main` which runs `Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120)).run()` until the host stops it

---

### Requirement: Plugin manifest structure

The system SHALL ship a root `manifest.yaml` declaring plugin metadata, tool provider registration, resource permissions, and runner metadata sufficient for Dify to load and execute the plugin.

#### Scenario: Required manifest fields

- **GIVEN** a valid plugin package root
- **WHEN** the manifest is parsed by a Dify-compatible toolchain
- **THEN** the manifest SHALL include `version`, `type: plugin`, `author`, `name`, `label` (multilingual map), `description` (multilingual), `icon`, `icon_dark`, `resource` (including `memory` and `permission` subtree), `plugins.tools` listing provider descriptors, and `meta` containing `version`, `arch`, `runner` (`language`, `version`, `entrypoint`), and `minimum_dify_version`

#### Scenario: Tool provider wiring

- **GIVEN** the manifest `plugins.tools` references the Agentcube provider descriptor
- **WHEN** the plugin is loaded
- **THEN** Dify SHALL resolve `provider/agentcube.yaml` and associate it with the Python module declared under `extra.python.source`

---

### Requirement: Provider descriptor structure

The system SHALL define a tool provider YAML that identifies the provider, lists its tools, and points to the Python provider implementation.

#### Scenario: Provider lists tools and entry module

- **GIVEN** `provider/agentcube.yaml` is present
- **WHEN** the integration runtime resolves the provider
- **THEN** the descriptor SHALL include `identity` (author, name, multilingual label/description, icon), a `tools` list including `tools/agentcube-code-interpreter.yaml`, and `extra.python.source: provider/agentcube.py`

---

### Requirement: Tool parameter schema

The system SHALL declare a tool schema for the code interpreter integration including connection endpoints, optional language selection, and code/command/session fields.

#### Scenario: Declared parameters match remote APIs

- **GIVEN** `tools/agentcube-code-interpreter.yaml`
- **WHEN** an operator configures the tool in Dify
- **THEN** the schema SHALL require string parameters `router_url` and `workload_manager_url`, SHALL offer optional `language` as a select among `python`, `javascript`, and `typescript`, and SHALL allow optional `code`, `command`, `session_id`, `session_reuse` (boolean), and `code_interpreter_id`, each documented for human and LLM-oriented forms

---

### Requirement: Tool provider credential validation

The system SHALL implement credential validation on the tool provider class and SHALL surface validation failures using the Dify tool provider error type.

#### Scenario: Invalid credentials are rejected

- **GIVEN** an instance of `AgentcubeCodeInterpreterProvider`
- **WHEN** `_validate_credentials` encounters an error condition the implementer treats as invalid
- **THEN** the provider SHALL raise `ToolProviderCredentialValidationError` with a string message derived from the failure

#### Scenario: Successful validation completes quietly

- **GIVEN** credentials that satisfy the provider’s validation rules
- **WHEN** `_validate_credentials` runs
- **THEN** the method SHALL return without raising

---

### Requirement: Tool invocation and JSON messaging

The system SHALL implement the Agentcube code interpreter tool as a Dify `Tool` that delegates execution and returns structured JSON to the host.

#### Scenario: Dify invokes the tool

- **GIVEN** a configured tool invocation with parameters matching the schema
- **WHEN** Dify calls `_invoke` on `AgentcubeCodeInterpreterTool`
- **THEN** the tool SHALL call `execute(**tool_parameters)` and SHALL yield `create_json_message(result)` for the outcome

---

### Requirement: Tool execution API surface

The system SHALL implement `execute` with parameters for router and workload manager URLs, optional language, session controls, and code or command execution, delegating to `agentcube.CodeInterpreterClient`.

#### Scenario: Code or command runs against configured endpoints

- **GIVEN** valid `router_url`, `workload_manager_url`, and optional `language` defaulting to `python`
- **WHEN** the tool receives `code` and/or `command` with optional `session_id`, `session_reuse`, and `code_interpreter_id`
- **THEN** the tool SHALL use the AgentCube Python SDK client to perform the corresponding remote operations and SHALL return a JSON-serializable result object suitable for `create_json_message`

---

### Requirement: Plugin Python dependencies

The system SHALL pin compatible versions of `dify-plugin` and `agentcube-sdk` for reproducible installs.

#### Scenario: Dependency bounds

- **GIVEN** `integrations/dify-plugin/requirements.txt`
- **WHEN** dependencies are installed in a clean environment
- **THEN** installs SHALL satisfy `dify-plugin>=0.4.2,<0.5.0` and `agentcube-sdk>=0.0.10`

---

### Requirement: PCAP analyzer FastAPI service

The system SHALL provide a FastAPI application that validates OpenAI-compatible configuration at startup, composes LangChain/LangGraph agents, and exposes an analysis endpoint for PCAP uploads.

#### Scenario: Startup requires API key

- **GIVEN** the process is started without a usable `OPENAI_API_KEY` (or equivalent configured API key)
- **WHEN** the application completes startup hooks
- **THEN** startup SHALL fail rather than serve requests without credentials

#### Scenario: Analyze endpoint accepts PCAP input

- **GIVEN** a running service with valid LLM configuration
- **WHEN** a client calls `POST /analyze` with either an uploaded PCAP file or a `pcap_path` form field
- **THEN** the handler SHALL return a body matching `AnalyzeResponse` including `script`, `results`, and `report`

---

### Requirement: PCAP analyzer configuration surface

The system SHALL read runtime configuration from environment variables for the OpenAI-compatible API, model selection, and AgentCube sandbox parameters.

#### Scenario: Defaults and overrides

- **GIVEN** standard deployment environment variables
- **WHEN** the service starts
- **THEN** it SHALL use `OPENAI_API_BASE` defaulting to `https://api.siliconflow.cn/v1`, `OPENAI_MODEL` defaulting to `Qwen/QwQ-32B`, `CODEINTERPRETER_NAME` defaulting to `my-interpreter`, `SANDBOX_NAMESPACE` defaulting to `default`, and `SANDBOX_WARMUP_SEC` defaulting to `5`, while binding HTTP to `0.0.0.0:8000` as defined in the application

---

### Requirement: PCAP analyzer sandbox integration

The system SHALL orchestrate PCAP analysis by planning and repairing scripts, executing them inside an AgentCube-backed sandbox via `SandboxRunner`, and aggregating results through reporter agents.

#### Scenario: Sandbox runner executes commands

- **GIVEN** a `SandboxRunner` constructed with interpreter name, namespace, and warmup duration
- **WHEN** analysis logic invokes `run` with a shell command
- **THEN** the runner SHALL execute the command in the remote sandbox context and SHALL return structured execution results for downstream LLM steps

#### Scenario: File staging uses runner uploads

- **GIVEN** a local PCAP path or bytes to analyze
- **WHEN** the orchestration needs the artifact inside the sandbox workspace
- **THEN** the system SHALL use `upload_file` or `upload_bytes` on `SandboxRunner` before executing analysis commands

---

### Requirement: PCAP analyzer container image

The system SHALL build a container image that installs Python dependencies with `uv`, vendors the in-repo `agentcube` SDK copy, sets `PYTHONPATH`, exposes port 8000, and starts the FastAPI app via `uv run`.

#### Scenario: Image entrypoint

- **GIVEN** the `example/pcap-analyzer/Dockerfile` build context
- **WHEN** the container runs without overriding the command
- **THEN** the default command SHALL be `uv run pcap_analyzer.py` with `PYTHONPATH="/app"` and port `8000` exposed

---

### Requirement: PCAP analyzer Kubernetes deployment

The system SHALL supply a `Deployment` manifest that runs the analyzer image with resource requests/limits and environment variables wired from a Secret and plain env for AgentCube and model endpoints.

#### Scenario: Deployment wiring

- **GIVEN** `example/pcap-analyzer/deployment.yaml` applied to the cluster
- **WHEN** the workload becomes ready
- **THEN** the pod SHALL run image `pcap-analyzer:latest` (pull `IfNotPresent`), listen on TCP 8000, request `cpu: 200m` / `memory: 100Mi` and limit `cpu: 1` / `memory: 1Gi`, mount `OPENAI_API_KEY` from Secret `pcap-analyzer-secrets` key `openai-api-key`, and set `OPENAI_API_BASE`, `OPENAI_MODEL`, `WORKLOAD_MANAGER_URL`, `ROUTER_URL`, `CODEINTERPRETER_NAME`, `SANDBOX_NAMESPACE`, and `SANDBOX_WARMUP_SEC` as container environment variables

#### Scenario: Process launch in cluster

- **GIVEN** the deployment’s container specification
- **WHEN** Kubernetes starts the container
- **THEN** the command SHALL be `uv` with arguments `run pcap_analyzer.py`, matching local Docker behavior
