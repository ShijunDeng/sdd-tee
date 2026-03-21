---
sidebar_position: 4
---

# Python SDK tutorial

Automate **CodeInterpreter** sessions with the `agentcube` Python package.

## Install

From the repository root:

```bash
pip install -e ./sdk-python
```

## Session lifecycle

`CodeInterpreterClient` is a **context manager**. Entering the context:

1. Calls the control plane to **create a session**
2. Constructs a **data-plane client** scoped to `/v1/namespaces/{ns}/code-interpreters/{id}/invocations/api/...`

Exiting deletes the remote session and closes HTTP sessions.

```python
from agentcube.code_interpreter import CodeInterpreterClient

with CodeInterpreterClient(
    control_plane_url="http://localhost:8080",
    namespace="default",
    headers={},
    create_body={"codeInterpreter": "demo-ci"},
) as ci:
    print(ci.interpreter_id)
    print(ci.run_code("print('ok')"))
```

## Commands and files

```python
ci.execute_command("uname -a")
ci.write_file("demo.txt", "hello")
print(ci.list_files("/workspace"))
raw = ci.download_file("/workspace/demo.txt")
```

`execute_command` raises `CommandExecutionError` when the remote exit code is non-zero.

## Error handling

```python
from agentcube.exceptions import DataPlaneError, CommandExecutionError

try:
    ci.execute_command("false")
except CommandExecutionError as e:
    print(e.exit_code, e.stderr)
except DataPlaneError as e:
    print("HTTP or JSON failure", e)
```

## Configuration tips

- Reuse **headers** for tracing (`traceparent`) and platform auth tokens.
- Match **`namespace`** to the `CodeInterpreter` object’s namespace.
- Align **`create_body`** with your Router’s session API (interpreter name, tenant id, resource class).

## Further reading

- `docs/devguide/code-interpreter-python-sdk.md` in the AgentCube repository
- `docs/devguide/code-interpreter-using-langchain.md` for LangChain-style tool wrappers
