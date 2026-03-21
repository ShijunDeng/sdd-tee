# AgentCube Python SDK — Design

Source root: `/tmp/agentcube-ref/sdk-python/`.

## Package layout

| Path | Role |
|------|------|
| `pyproject.toml` | Package `agentcube-sdk`, dependencies |
| `agentcube/__init__.py` | Public exports |
| `agentcube/code_interpreter.py` | `CodeInterpreterClient` |
| `agentcube/agent_runtime.py` | `AgentRuntimeClient` |
| `agentcube/exceptions.py` | Exception classes |
| `agentcube/clients/__init__.py` | Re-exports client classes |
| `agentcube/clients/control_plane.py` | `ControlPlaneClient` |
| `agentcube/clients/code_interpreter_data_plane.py` | `CodeInterpreterDataPlaneClient` |
| `agentcube/clients/agent_runtime_data_plane.py` | `AgentRuntimeDataPlaneClient` |
| `agentcube/utils/http.py` | `create_session` |
| `agentcube/utils/utils.py` | `read_token_from_file` |
| `agentcube/utils/log.py` | `get_logger` |
| `agentcube/utils/__init__.py` | Empty (module marker) |
| `examples/basic_usage.py`, `examples/agent_runtime_usage.py`, `scripts/e2e_picod_test.py`, `tests/*.py` | Non-library artifacts |

## Public exports (`agentcube/__init__.py`)

```python
from .code_interpreter import CodeInterpreterClient
from .agent_runtime import AgentRuntimeClient

__all__ = ["CodeInterpreterClient", "AgentRuntimeClient"]
```

`agentcube/clients/__init__.py` additionally exports (not in root `__all__`):

```python
__all__ = [
    "ControlPlaneClient",
    "CodeInterpreterDataPlaneClient",
    "AgentRuntimeDataPlaneClient",
]
```

## Configuration (no single `Configuration` class)

There is **no** dedicated configuration dataclass. Defaults and environment resolution are distributed across:

| Component | Resolved settings |
|-----------|-------------------|
| `ControlPlaneClient` | `base_url` ← `workload_manager_url` or `WORKLOAD_MANAGER_URL`; `Authorization` ← `auth_token` or SA token file; `timeout=120`, `connect_timeout=5.0`, `pool_connections=10`, `pool_maxsize=10` |
| `CodeInterpreterClient` | `router_url` ← arg or `ROUTER_URL` (required); `workload_manager_url` / `auth_token` passed to `ControlPlaneClient`; `name`, `namespace`, `ttl`, `verbose`, `session_id` |
| `CodeInterpreterDataPlaneClient` | `timeout=120`, `connect_timeout=5.0`, `pool_connections=10`, `pool_maxsize=10`; `base_url` from `base_url` **or** `router_url`+`namespace`+`cr_name` |
| `AgentRuntimeClient` | `router_url` ← arg or `ROUTER_URL`; `timeout=120`, `connect_timeout=5.0` passed to data plane |
| `AgentRuntimeDataPlaneClient` | same timeout defaults as above |

## `CodeInterpreterClient` (`agentcube/code_interpreter.py`)

```python
class CodeInterpreterClient:
    def __init__(
        self,
        name: str = "my-interpreter",
        namespace: str = "default",
        ttl: int = 3600,
        workload_manager_url: Optional[str] = None,
        router_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        verbose: bool = False,
        session_id: Optional[str] = None,
    ): ...

    def _init_data_plane(self) -> None: ...

    def __enter__(self): ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    def stop(self) -> None: ...

    def execute_command(self, command: str, timeout: Optional[float] = None) -> str: ...
    def run_code(self, language: str, code: str, timeout: Optional[float] = None) -> str: ...
    def write_file(self, content: str, remote_path: str) -> None: ...
    def upload_file(self, local_path: str, remote_path: str) -> None: ...
    def download_file(self, remote_path: str, local_path: str) -> None: ...
    def list_files(self, path: str = "."): ...
```

**Fields set on instance:** `name`, `namespace`, `ttl`, `verbose`, `logger`, `cp_client`, `router_url`, `session_id`, `dp_client`.

## `AgentRuntimeClient` (`agentcube/agent_runtime.py`)

```python
class AgentRuntimeClient:
    def __init__(
        self,
        agent_name: str,
        namespace: str = "default",
        router_url: Optional[str] = None,
        verbose: bool = False,
        session_id: Optional[str] = None,
        timeout: int = 120,
        connect_timeout: float = 5.0,
    ): ...

    def __enter__(self): ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    def invoke(self, payload: Dict[str, Any], timeout: Optional[float] = None) -> Any: ...

    def close(self) -> None: ...
```

**Fields:** `agent_name`, `namespace`, `timeout`, `connect_timeout`, `logger`, `router_url`, `session_id`, `dp_client`.

## `ControlPlaneClient` (`agentcube/clients/control_plane.py`)

```python
class ControlPlaneClient:
    def __init__(
        self,
        workload_manager_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: int = 120,
        connect_timeout: float = 5.0,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ): ...

    def create_session(
        self,
        name: str = "my-interpreter",
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        ttl: int = 3600,
    ) -> str: ...

    def delete_session(self, session_id: str) -> bool: ...

    def close(self) -> None: ...
```

### Control plane — HTTP

| Method | Path | Notes |
|--------|------|-------|
| `POST` | `{base_url}/v1/code-interpreter` | JSON body: `name`, `namespace`, `ttl`, `metadata` |
| `DELETE` | `{base_url}/v1/code-interpreter/sessions/{session_id}` | 404 treated as success in `delete_session` |

**Headers (default on `self.session`):**

- `Content-Type`: `application/json`
- `Authorization`: `Bearer {token}` if token non-empty

**Timeout:** `(connect_timeout, timeout)` on each request.

## `CodeInterpreterDataPlaneClient` (`agentcube/clients/code_interpreter_data_plane.py`)

```python
class CodeInterpreterDataPlaneClient:
    def __init__(
        self,
        session_id: str,
        router_url: Optional[str] = None,
        namespace: Optional[str] = None,
        cr_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 120,
        connect_timeout: float = 5.0,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ): ...

    def _request(self, method: str, endpoint: str, body: Optional[bytes] = None, **kwargs) -> requests.Response: ...

    def execute_command(self, command: Union[str, List[str]], timeout: Optional[float] = None) -> str: ...
    def run_code(self, language: str, code: str, timeout: Optional[float] = None) -> str: ...
    def write_file(self, content: str, remote_path: str) -> None: ...
    def upload_file(self, local_path: str, remote_path: str) -> None: ...
    def download_file(self, remote_path: str, local_path: str) -> None: ...
    def list_files(self, path: str = ".") -> Any: ...
    def close(self) -> None: ...
```

### Data plane (Code Interpreter) — base URL

If `base_url` is not provided:

```text
base_path = "/v1/namespaces/{namespace}/code-interpreters/{cr_name}/invocations/"
self.base_url = urljoin(router_url, base_path)
```

### Data plane — HTTP (relative to `self.base_url`)

| Method | Relative path | Body / params |
|--------|---------------|---------------|
| `POST` | `api/execute` | JSON `{"command": [...], "timeout": "<n>s"}` |
| `POST` | `api/files` | JSON `{"path", "content" (base64), "mode": "0644"}` |
| `POST` | `api/files` (multipart) | `files={'file': ...}`, `data={'path', 'mode'}` |
| `GET` | `api/files/{clean_path}` | `stream=True` for download (`clean_path = remote_path.lstrip("/")`) |
| `GET` | `api/files` | query `path` |

**Headers:**

- Default session header: `x-agentcube-session-id: {session_id}`
- JSON requests: `Content-Type: application/json` when `body` is set in `_request`
- Multipart upload: `x-agentcube-session-id` only (no JSON Content-Type on the outer request)

**Note:** Docstring states Router handles JWT; SDK does not set `Authorization` on data plane.

## `AgentRuntimeDataPlaneClient` (`agentcube/clients/agent_runtime_data_plane.py`)

```python
class AgentRuntimeDataPlaneClient:
    SESSION_HEADER = "x-agentcube-session-id"

    def __init__(
        self,
        router_url: str,
        namespace: str,
        agent_name: str,
        timeout: int = 120,
        connect_timeout: float = 5.0,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ): ...

    def bootstrap_session_id(self) -> str: ...

    def invoke(
        self,
        session_id: str,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> requests.Response: ...

    def close(self) -> None: ...
```

### Data plane (Agent Runtime) — base URL

```text
base_path = f"/v1/namespaces/{namespace}/agent-runtimes/{agent_name}/invocations/"
self.base_url = urljoin(router_url, base_path)
```

### Data plane — HTTP

| Method | URL | Headers | Body |
|--------|-----|---------|------|
| `GET` | `self.base_url` | (session default headers only) | — |
| `POST` | `self.base_url` | `x-agentcube-session-id`, `Content-Type: application/json` | `json=payload` |

**Timeouts:** `(connect_timeout, timeout)` where `timeout` for `invoke` read side is the method argument or `self.timeout`.

## `create_session` (`agentcube/utils/http.py`)

```python
def create_session(
    pool_connections: int = 10,
    pool_maxsize: int = 10,
) -> requests.Session: ...
```

Mounts `HTTPAdapter` for `http://` and `https://`.

## `read_token_from_file` (`agentcube/utils/utils.py`)

```python
def read_token_from_file(file_path: str) -> str: ...
```

Returns file contents stripped, or `""` on `FileNotFoundError`.

## `get_logger` (`agentcube/utils/log.py`)

```python
def get_logger(name: str, level: Union[int, str] = logging.INFO) -> logging.Logger: ...
```

## Exception hierarchy (`agentcube/exceptions.py`)

```python
class AgentCubeError(Exception):
    """Base exception for AgentCube SDK"""
    pass

class CommandExecutionError(AgentCubeError):
    def __init__(self, exit_code, stderr, command=None):
        self.exit_code = exit_code
        self.stderr = stderr
        self.command = command
        super().__init__(f"Command failed (exit {exit_code}): {stderr}")

class SessionError(AgentCubeError):
    """Raised when session creation or management fails"""
    pass

class DataPlaneError(AgentCubeError):
    """Raised when Data Plane operations fail"""
    pass
```

## Dependencies (`sdk-python/pyproject.toml`)

```toml
dependencies = [
    "requests",
    "PyJWT>=2.0.0",
    "cryptography",
]
```

- `requires-python = ">=3.10"`
- Build: `setuptools>=61.0`, `wheel`; backend `setuptools.build_meta`
- Packages: `where = ["."]`, `include = ["agentcube*"]`, `namespaces = false`
