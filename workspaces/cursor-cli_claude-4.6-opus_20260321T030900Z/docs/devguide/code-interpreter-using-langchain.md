# Using AgentCube CodeInterpreter with LangChain

This guide shows how to wrap **`CodeInterpreterClient`** as a **LangChain**-style tool so LLM agents can execute code in an **AgentCube-managed** sandbox instead of on the developer laptop.

> LangChain APIs evolve; the patterns below use generic **tool** and **agent** concepts compatible with LangChain / LangGraph-style applications.

## Prerequisites

- Running AgentCube **Router** and a **`CodeInterpreter`** CR in your cluster
- `pip install langchain langchain-core langchain-openai agentcube-sdk` (adjust provider packages as needed)
- Network path from the process running LangChain to the Router (VPN, port-forward, or in-cluster)

## Design pattern

1. **One session per user turn** (simple, safe) — create `CodeInterpreterClient` inside the tool callable and exit before returning. Higher latency.
2. **One session per agent run** (efficient) — hold `CodeInterpreterClient` in your orchestration state (LangGraph `StateGraph`) and pass a thin wrapper into tools; close on graph completion.

For production, prefer **(2)** with explicit idle timeouts aligned with `CodeInterpreter.spec.sessionTimeout`.

## Minimal tool wrapper (LangChain `StructuredTool`)

```python
from __future__ import annotations

from typing import Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from agentcube.code_interpreter import CodeInterpreterClient


class RunSandboxCodeInput(BaseModel):
    code: str = Field(description="Python code to run in the remote interpreter.")
    cwd: Optional[str] = Field(default=None, description="Optional working directory.")


def make_run_sandbox_code_tool(
    router_url: str,
    namespace: str,
    interpreter_create_body: dict,
    headers: dict | None = None,
):
    def _run(code: str, cwd: Optional[str] = None) -> str:
        with CodeInterpreterClient(
            control_plane_url=router_url,
            namespace=namespace,
            headers=headers,
            create_body=interpreter_create_body,
        ) as client:
            if cwd:
                client.execute_command("true", cwd=cwd)
            result = client.run_code(code, language="python")
            return str(result)

    return StructuredTool.from_function(
        name="run_sandbox_python",
        description="Execute Python in an AgentCube CodeInterpreter sandbox. "
        "Use for calculations, data parsing, and safe file generation.",
        func=_run,
        args_schema=RunSandboxCodeInput,
    )
```

Register `make_run_sandbox_code_tool(...)` with your agent’s tool list.

## File-oriented tools

Expose separate tools for **`write_file`**, **`upload_file`**, and **`download_file`** so the model can stage datasets (for example PCAP or CSV) before analysis. Keep **path validation** in your tool layer: restrict to a subdirectory like `/workspace/job`.

## LangGraph state (sketch)

```python
from typing import TypedDict

from agentcube.code_interpreter import CodeInterpreterClient


class AgentState(TypedDict, total=False):
    messages: list
    sandbox: CodeInterpreterClient | None


def teardown_sandbox(state: AgentState) -> AgentState:
    sb = state.get("sandbox")
    if sb:
        sb.stop()
    return {**state, "sandbox": None}
```

Use **teardown** in a `finally` path or graph edge so sessions are always deleted.

## Security checklist

- **Authenticate** the Router with your platform’s OIDC or mTLS; do not embed long-lived cluster admin credentials in the tool process.
- Set **`authMode: picod`** on `CodeInterpreter` so PicoD rejects unsigned calls.
- Treat all model-produced code as **untrusted**; combine AgentCube isolation with **NetworkPolicy** and **Pod Security** standards.

## Observability

- Propagate **W3C trace context** headers from LangChain / your framework into `CodeInterpreterClient(..., headers=...)`.
- Log `interpreter_id` per session for correlation with Router and workload manager logs.

## Further reading

- [CodeInterpreter Python SDK](./code-interpreter-python-sdk.md)
- [PicoD proposal](../design/picod-proposal.md)
