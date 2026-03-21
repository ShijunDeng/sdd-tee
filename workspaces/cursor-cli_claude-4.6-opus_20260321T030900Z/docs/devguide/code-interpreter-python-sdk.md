# CodeInterpreter Python SDK

The **`CodeInterpreterClient`** in `sdk-python/agentcube/code_interpreter.py` is the high-level API for **creating a session**, running **commands and code**, and managing **files** in a remote interpreter sandbox through the AgentCube Router.

## Installation

From the repository root:

```bash
pip install -e ./sdk-python
```

Or add `sdk-python` as a path dependency in your project.

## Dependencies

Uses `requests` for HTTP. See `sdk-python/requirements.txt`.

## Concepts

1. **Control plane** — `ControlPlaneClient` talks to the Router base URL to **create** and **delete** sessions.
2. **Data plane** — After session creation, `CodeInterpreterDataPlaneClient` calls routes under:

   `/v1/namespaces/{namespace}/code-interpreters/{interpreter_id}/invocations/api/...`

3. **Context manager** — `CodeInterpreterClient` ties session lifetime to a `with` block so sessions are deleted on exit.

## Basic usage

```python
from agentcube.code_interpreter import CodeInterpreterClient

ROUTER = "https://agentcube-router.example.com"  # or in-cluster Service URL
NS = "default"

with CodeInterpreterClient(
    control_plane_url=ROUTER,
    namespace=NS,
    headers={"Authorization": "Bearer <platform-token>"},  # if required by your deployment
    create_body={"codeInterpreter": "my-interpreter"},  # shape depends on control-plane API
) as client:
    print("session:", client.interpreter_id)
    out = client.run_code("print(1 + 1)", language="python")
    print(out)
    client.write_file("notes.txt", "hello from sdk")
    data = client.download_file("notes.txt")
    assert data == b"hello from sdk"
```

Replace `create_body` with the JSON your Router expects for session creation (interpreter name, labels, resource class, etc.).

## API reference

### Constructor

`CodeInterpreterClient(control_plane_url, namespace, headers=None, create_body=None)`

- **`control_plane_url`** — Router root (no trailing slash required; clients normalize).
- **`namespace`** — Kubernetes namespace of the `CodeInterpreter` resource.
- **`headers`** — Extra HTTP headers (auth, tracing).
- **`create_body`** — JSON payload for `create_session`.

### Session lifecycle

| Method | Description |
|--------|-------------|
| `__enter__` | Creates session; builds data-plane client; returns `self`. |
| `stop()` / `__exit__` | Closes data-plane client; deletes remote session by id. |
| `interpreter_id` | Property — session / interpreter id from create response. |

### Execution and files

| Method | Description |
|--------|-------------|
| `execute_command(command, cwd=None)` | Shell command; raises `CommandExecutionError` on non-zero exit. |
| `run_code(code, language="python")` | Interpreted execution. |
| `write_file(path, content)` | Text write. |
| `upload_file(path, data, filename=None)` | Multipart binary upload. |
| `download_file(path) -> bytes` | Download file contents. |
| `list_files(path=".")` | Directory listing. |

## Errors

- **`DataPlaneError`** — HTTP 4xx/5xx or invalid JSON from data-plane routes.
- **`CommandExecutionError`** — Non-zero exit from `execute_command` (includes `exit_code`, `stderr`).

## Testing against a dev cluster

1. Deploy AgentCube Helm chart with Redis configured.
2. Apply a `CodeInterpreter` CR with `authMode: picod` and a test image.
3. Port-forward the Router Service or call it from a pod in the cluster.
4. Use the same `namespace` and interpreter name as in your CR.

## See also

- `agentcube/clients/code_interpreter_data_plane.py` — URL layout and HTTP verbs
- `agentcube/clients/control_plane.py` — session create/delete
- `docs/design/picod-proposal.md` — backend execution API
