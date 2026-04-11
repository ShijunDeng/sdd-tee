# AR-033: Python SDK — Clients and Exceptions

**Module**: root  
**Language**: Python  
**Size**: M (11 files)  
**Status**: ST-3 completed  

---

## Tasks

### T001: Project scaffolding and package metadata
- [ ] Create `sdk-python/pyproject.toml` with build-system, project metadata, and dependencies
- [ ] Verify `name = "agentcube-sdk"`, `version = "0.0.10"`, `requires-python = ">=3.10"`
- [ ] Verify dependencies: `requests>=2.31.0`, dev deps: `pytest>=7.0.0`, `pytest-cov>=4.0.0`
- [ ] Verify `build-backend = "setuptools.build_meta"`

### T002: Package initialization and public API exports
- [ ] Create `sdk-python/agentcube/__init__.py`
- [ ] Export `CodeInterpreterClient` and `AgentRuntimeClient` in `__all__`
- [ ] Verify imports resolve correctly: `from agentcube import CodeInterpreterClient, AgentRuntimeClient`

### T003: Exception hierarchy
- [ ] Create `sdk-python/agentcube/exceptions.py`
- [ ] Define `AgentCubeError(Exception)` as base exception
- [ ] Define `CommandExecutionError(AgentCubeError)` with `exit_code`, `stderr`, `command` constructor params
- [ ] Define `SessionError(AgentCubeError)` for session-related errors
- [ ] Define `DataPlaneError(AgentCubeError)` for data plane errors
- [ ] Verify all exceptions inherit from `AgentCubeError`
- [ ] Verify `CommandExecutionError` stores all three attributes as instance variables

### T004: Control plane client
- [ ] Create `sdk-python/agentcube/clients/__init__.py`
- [ ] Create `sdk-python/agentcube/clients/control_plane.py`
- [ ] Implement `ControlPlaneClient.__init__(workload_manager_url, auth_token=None)`:
  - [ ] Resolve URL from arg or `WORKLOAD_MANAGER_URL` env var
  - [ ] Resolve token from arg or `/var/run/secrets/kubernetes.io/serviceaccount/token`
  - [ ] Create `requests.Session` with connection pooling
  - [ ] Set `Authorization: Bearer {token}` header if token present
- [ ] Implement `create_session(name, namespace, metadata=None, ttl=3600) -> str`:
  - [ ] POST to `/v1/code-interpreter` with JSON `{name, namespace, ttl, metadata}`
  - [ ] Return `data["sessionId"]` or raise `ValueError`
- [ ] Implement `delete_session(session_id) -> bool`:
  - [ ] DELETE to `/v1/code-interpreter/sessions/{session_id}`
  - [ ] Return `True` on 404 or success, `False` on other errors

### T005: Code Interpreter data plane client
- [ ] Create `sdk-python/agentcube/clients/code_interpreter_data_plane.py`
- [ ] Implement `CodeInterpreterDataPlaneClient.__init__(router_url, namespace, cr_name, session_id, timeout=120, connect_timeout=5.0)`:
  - [ ] Build base URL using `urljoin`
  - [ ] Create `requests.Session`
  - [ ] Set default header `x-agentcube-session-id: {session_id}`
- [ ] Implement `_request(method, path, **kwargs)`:
  - [ ] Add timeout tuple `(connect_timeout, read_timeout)`
  - [ ] Raise on HTTP errors
- [ ] Implement `execute_command(command, timeout=None) -> dict`:
  - [ ] POST to `api/execute` with JSON `{command: [...], timeout: "<n>s"}`
  - [ ] Raise `CommandExecutionError` if `exit_code != 0`
- [ ] Implement `write_file(path, content, mode="0644")`:
  - [ ] POST to `api/files` with base64-encoded content
- [ ] Implement `upload_file(local_path, remote_path)`:
  - [ ] Multipart POST to `api/files`
- [ ] Implement `download_file(remote_path, local_path)`:
  - [ ] GET from `api/files/{path}`, stream response to file
- [ ] Implement `list_files(path) -> list`:
  - [ ] GET from `api/files?path={path}`

### T006: Agent Runtime data plane client
- [ ] Create `sdk-python/agentcube/clients/agent_runtime_data_plane.py`
- [ ] Implement `AgentRuntimeDataPlaneClient`:
  - [ ] Class constant `SESSION_HEADER = "x-agentcube-session-id"`
  - [ ] `__init__(router_url, namespace, agent_name, session_id, timeout=120, connect_timeout=5.0)`:
    - [ ] Build invocation base URL
    - [ ] Create `requests.Session`
  - [ ] `_request(method, path, **kwargs)`:
    - [ ] Add timeout tuple
  - [ ] `invoke(payload, timeout=None) -> dict`:
    - [ ] POST JSON to invocation URL
    - [ ] Set `SESSION_HEADER` and `Content-Type` headers

### T007: HTTP utility functions
- [ ] Create `sdk-python/agentcube/utils/__init__.py`
- [ ] Create `sdk-python/agentcube/utils/http.py`
- [ ] Implement `read_token_from_file(path) -> str | None`:
  - [ ] Read file, return stripped contents
  - [ ] Handle `FileNotFoundError`, return `None`
- [ ] Implement `create_session(timeout=120, connect_timeout=5.0) -> tuple`:
  - [ ] Create `requests.Session`
  - [ ] Mount `HTTPAdapter` with pool settings
  - [ ] Return `(session, timeout)` tuple

### T008: General utility functions
- [ ] Create `sdk-python/agentcube/utils/utils.py`
- [ ] Implement `ensure_dir(path)`: create directory if not exists
- [ ] Implement `generate_timestamp() -> str`: ISO format timestamp
- [ ] Implement `base64_encode(data) -> str`: standard base64 encoding
- [ ] Implement `base64_decode(s) -> bytes`: standard base64 decoding

### T009: Logging configuration
- [ ] Create `sdk-python/agentcube/utils/log.py`
- [ ] Implement `setup_logging(level=logging.INFO)`:
  - [ ] Configure root logger with format
  - [ ] Return logger instance

### T010: High-level Code Interpreter client
- [ ] Create `sdk-python/agentcube/code_interpreter.py`
- [ ] Implement `CodeInterpreterClient.__init__(router_url, workload_manager_url=None, name=None, namespace="default", session_id=None, ttl=3600, timeout=120)`:
  - [ ] Validate `router_url` is provided (arg or `ROUTER_URL` env)
  - [ ] Store config
  - [ ] If `session_id` not provided:
    - [ ] Create `ControlPlaneClient`
    - [ ] Call `create_session()`
    - [ ] Handle failure: delete session, re-raise
  - [ ] Call `_init_data_plane()`
- [ ] Implement `_init_data_plane()`:
  - [ ] Create `CodeInterpreterDataPlaneClient` with `session_id`
- [ ] Implement context manager protocol:
  - [ ] `__enter__()`: return `self`
  - [ ] `__exit__(exc_type, exc_val, exc_tb)`: call `stop()`
- [ ] Implement `stop()`:
  - [ ] Close data plane session
  - [ ] If created session: call `delete_session()`
  - [ ] Close control plane session
- [ ] Implement `execute_command(command, timeout=None) -> dict`: delegate to data plane
- [ ] Implement `run_code(code, language="python") -> dict`:
  - [ ] Write timestamped `.py` file
  - [ ] Execute `python3 <file>`
- [ ] Implement `write_file(path, content)`: delegate to data plane
- [ ] Implement `upload_file(local_path, remote_path)`: delegate to data plane
- [ ] Implement `download_file(remote_path, local_path)`: delegate to data plane
- [ ] Implement `list_files(path) -> list`: delegate to data plane

### T011: High-level Agent Runtime client
- [ ] Create `sdk-python/agentcube/agent_runtime.py`
- [ ] Implement `AgentRuntimeClient.__init__(router_url, namespace, agent_name, session_id=None, timeout=120, connect_timeout=5.0)`:
  - [ ] Store config
  - [ ] If `session_id` not provided:
    - [ ] GET from invocation base URL
    - [ ] Read `x-agentcube-session-id` from response header
    - [ ] Raise `ValueError` if missing
  - [ ] Create `AgentRuntimeDataPlaneClient`
- [ ] Implement context manager protocol:
  - [ ] `__enter__()`: return `self`
  - [ ] `__exit__(exc_type, exc_val, exc_tb)`: call `close()`
- [ ] Implement `close()`: close underlying session
- [ ] Implement `invoke(payload, timeout=None) -> dict`:
  - [ ] If no `session_id`: raise `ValueError`
  - [ ] Delegate to data plane

---

## Verification

- [ ] All 11 files created and match specifications
- [ ] `pyproject.toml` valid TOML, installable via `pip install -e sdk-python/`
- [ ] All imports resolve: `from agentcube import CodeInterpreterClient, AgentRuntimeClient`
- [ ] Exception hierarchy testable: all custom exceptions inherit from `AgentCubeError`
- [ ] Context managers work: `with CodeInterpreterClient(...) as client:` and `with AgentRuntimeClient(...) as client:`
- [ ] No circular imports between modules
- [ ] All HTTP clients use connection pooling
- [ ] Token resolution from file path works (with graceful fallback)
- [ ] Environment variable fallbacks work for URLs and tokens
