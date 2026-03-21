# AgentCube Python SDK Specification

## Purpose

Python client library (`agentcube-sdk`) for creating Code Interpreter sessions via the Workload Manager (control plane) and executing code/files via the Router (data plane), plus invoking AgentRuntime workloads through the Router.

## Requirements

### Requirement: `CodeInterpreterClient` lifecycle
The system SHALL construct a client that either reuses `session_id` or creates a session via `ControlPlaneClient.create_session`, then initializes `CodeInterpreterDataPlaneClient` with header `x-agentcube-session-id`.

#### Scenario: Context manager cleanup
- **GIVEN** `CodeInterpreterClient` is used as a context manager
- **WHEN** the block exits (with or without exception)
- **THEN** `__exit__` SHALL call `stop()`, which closes the data-plane session, deletes the control-plane session if `session_id` was set, and closes the control plane HTTP session

#### Scenario: Data plane init failure after session create
- **GIVEN** `session_id` was not provided and `create_session` succeeded
- **WHEN** `_init_data_plane()` raises
- **THEN** the client SHALL log a warning, call `delete_session(session_id)`, set `session_id` to `None`, and re-raise

#### Scenario: Router URL required
- **GIVEN** neither `router_url` nor environment variable `ROUTER_URL` is set
- **WHEN** `CodeInterpreterClient.__init__` runs
- **THEN** it SHALL raise `ValueError` explaining that Router URL must be provided via argument or `ROUTER_URL`

### Requirement: Code Interpreter — execute, files, stop
The system SHALL expose `execute_command`, `run_code`, `write_file`, `upload_file`, `download_file`, `list_files`, and `stop` delegating to the data plane client where applicable.

#### Scenario: Command non-zero exit
- **GIVEN** `execute_command` receives a response with `exit_code != 0`
- **WHEN** the response JSON is parsed
- **THEN** the system SHALL raise `CommandExecutionError` with `exit_code`, `stderr`, and `command`

#### Scenario: Python code execution path
- **GIVEN** `language` is `python`, `py`, or `python3`
- **WHEN** `run_code` runs
- **THEN** the system SHALL write a timestamped `.py` file via `write_file` and execute `python3 <file>` through `execute_command`

### Requirement: `AgentRuntimeClient` lifecycle
The system SHALL bootstrap or reuse `session_id` from the Agent Runtime invocation endpoint via `GET` on the base invocation URL, then `POST` JSON payloads with session header.

#### Scenario: Context manager
- **GIVEN** `AgentRuntimeClient` is used as a context manager
- **WHEN** the block exits
- **THEN** `close()` SHALL close the underlying `requests.Session`

#### Scenario: Bootstrap session id
- **GIVEN** `session_id` is not provided
- **WHEN** the client initializes
- **THEN** it SHALL `GET` `{router}/v1/namespaces/{namespace}/agent-runtimes/{agent_name}/invocations/` and read header `x-agentcube-session-id`; if missing, raise `ValueError` with message `Missing required response header: x-agentcube-session-id`

#### Scenario: Invoke without session
- **GIVEN** `session_id` is falsy
- **WHEN** `invoke` is called
- **THEN** it SHALL raise `ValueError("AgentRuntime session_id is not initialized")`

### Requirement: HTTP client contracts — control plane
The system SHALL use `requests.Session` with connection pooling (`HTTPAdapter`) for Workload Manager calls.

#### Scenario: Create session
- **GIVEN** `ControlPlaneClient.create_session(name, namespace, metadata=None, ttl=3600)`
- **WHEN** the request succeeds
- **THEN** the client SHALL `POST {base_url}/v1/code-interpreter` with JSON body `{"name","namespace","ttl","metadata"}` and return `data["sessionId"]` or raise `ValueError` if absent

#### Scenario: Delete session
- **GIVEN** `delete_session(session_id)`
- **WHEN** the server returns 404
- **THEN** the method SHALL return `True`; on other failures it SHALL log and return `False`

#### Scenario: Workload Manager URL and auth
- **GIVEN** `workload_manager_url` and `auth_token` may be omitted
- **WHEN** the client initializes
- **THEN** `base_url` SHALL resolve from `workload_manager_url` or `WORKLOAD_MANAGER_URL`; token SHALL resolve from `auth_token` or `/var/run/secrets/kubernetes.io/serviceaccount/token` via `read_token_from_file`, and if present set `Authorization: Bearer {token}`

### Requirement: HTTP client contracts — data plane (Code Interpreter)
The system SHALL target Router-relative paths under `{base_url}` derived from `urljoin(router_url, "/v1/namespaces/{ns}/code-interpreters/{cr_name}/invocations/")` unless `base_url` is passed explicitly.

#### Scenario: Execute command
- **WHEN** `execute_command` posts to `api/execute`
- **THEN** the body SHALL be JSON `{"command": [...], "timeout": "<n>s"}` and read timeout SHALL be `timeout_value + 2.0` seconds when numeric (to avoid `ReadTimeout` before PicoD returns exit 124)

#### Scenario: Files API
- **WHEN** `write_file` runs
- **THEN** it SHALL `POST api/files` with base64 `content`, `path`, `mode` `"0644"`
- **WHEN** `upload_file` runs
- **THEN** it SHALL `POST` multipart to `api/files` with headers including `x-agentcube-session-id`

### Requirement: HTTP client contracts — data plane (Agent Runtime)
The system SHALL `POST` JSON to the invocation base URL with headers `x-agentcube-session-id` and `Content-Type: application/json`.

#### Scenario: Invoke timeout tuple
- **GIVEN** `invoke(..., timeout=None)`
- **WHEN** the request is sent
- **THEN** `timeout` SHALL be `(connect_timeout, self.timeout)` where `self.timeout` defaults to `120`

### Requirement: Session header management
The system SHALL use lowercase header name `x-agentcube-session-id` for SDK Router requests (`CodeInterpreterDataPlaneClient` default session header; `AgentRuntimeDataPlaneClient` uses class constant `SESSION_HEADER = "x-agentcube-session-id"`).

#### Scenario: Code Interpreter session header
- **GIVEN** `CodeInterpreterDataPlaneClient` is constructed
- **WHEN** any `_request` or upload runs
- **THEN** the session SHALL include `x-agentcube-session-id: {session_id}` (upload sets it explicitly on the multipart POST)

### Requirement: Exception hierarchy
The system SHALL define `AgentCubeError`, `CommandExecutionError`, `SessionError`, and `DataPlaneError` in `agentcube.exceptions`.

#### Scenario: Command failure
- **GIVEN** remote command returns non-zero exit code in JSON
- **WHEN** `execute_command` processes the response
- **THEN** it SHALL raise `CommandExecutionError` (subclass of `AgentCubeError`)

#### Scenario: SessionError / DataPlaneError usage
- **GIVEN** the current package sources under `agentcube/`
- **WHEN** searching for `raise SessionError` / `raise DataPlaneError`
- **THEN** these classes are defined for extension but not raised by the core client modules in the extracted tree (callers MAY rely on `ValueError`, `requests` exceptions, or `CommandExecutionError`)

### Requirement: Timeout behavior
The system SHALL default control-plane and data-plane read timeouts to `120` seconds and connect timeout to `5.0` seconds unless overridden per call.

#### Scenario: Per-call override for code execution
- **GIVEN** `execute_command(command, timeout=None)`
- **WHEN** `timeout` is `None`
- **THEN** the effective timeout value SHALL default to `self.timeout` (`120`) for constructing the PicoD timeout string and read-timeout buffer logic

#### Scenario: AgentRuntimeClient constructor timeouts
- **GIVEN** `AgentRuntimeClient(..., timeout=120, connect_timeout=5.0)`
- **WHEN** `invoke` is called without `timeout`
- **THEN** read timeout SHALL be `120` (instance default)

---

**Public package surface:** `agentcube/__init__.py` exports only `CodeInterpreterClient` and `AgentRuntimeClient` in `__all__`.
