# AgentCube Integrations — Design

Sources: `/tmp/agentcube-ref/integrations/dify-plugin/`, `/tmp/agentcube-ref/example/pcap-analyzer/`.

## Dify plugin — file map

| File | Role |
|------|------|
| `main.py` | `Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120)).run()` |
| `manifest.yaml` | Root plugin manifest for Dify |
| `provider/agentcube.yaml` | Tool provider identity + tool list + Python entry |
| `provider/agentcube.py` | `AgentcubeCodeInterpreterProvider` |
| `tools/agentcube-code-interpreter.yaml` | Tool parameter schema |
| `tools/agentcube-code-interpreter.py` | `AgentcubeCodeInterpreterTool` |
| `requirements.txt` | `dify-plugin` + `agentcube-sdk` pins |
| `GUIDE.md`, `README.md`, `PRIVACY.md`, `.difyignore` | Docs / packaging |

## `manifest.yaml` structure (exact top-level keys)

From source:

- `version`: `0.0.2`
- `type`: `plugin`
- `author`: `volcano-sh`
- `name`: `agentcube`
- `label`: map `en_US`, `ja_JP`, `zh_Hans`, `pt_BR` → `Agentcube`
- `description`: multilingual strings (AgentCube description)
- `icon`: `icon.png`
- `icon_dark`: `icon-dark.png`
- `resource`: `memory`, `permission` subtree (`tool`, `model`, `endpoint`, `app`, `storage` flags and sizes)
- `plugins.tools`: list `[provider/agentcube.yaml]`
- `meta`: `version`, `arch` (`amd64`, `arm64`), `runner` (`language: python`, `version: "3.12"`, `entrypoint: main`), `minimum_dify_version: null`
- `created_at`, `privacy`, `repo`, `verified`

## `provider/agentcube.yaml` structure

- `identity`: `author`, `name`, `label` (multilingual), `description` (multilingual), `icon`
- Commented `oauth_schema` block (not active)
- `tools`: list `[tools/agentcube-code-interpreter.yaml]`
- `extra.python.source`: `provider/agentcube.py`

## Tool definition (`tools/agentcube-code-interpreter.yaml`)

- `identity.name`: `agentcube-code-interpreter`
- `identity.author`: `agentcube`
- `identity.label` / `description` (human + llm strings)
- `parameters` (each has `name`, `type`, `required`, `label`, `human_description`, `llm_description`, `form`):

| name | type | required | form | notes |
|------|------|----------|------|-------|
| `router_url` | string | true | form | |
| `workload_manager_url` | string | true | form | |
| `language` | select | false | llm | options: `python`, `javascript`, `typescript` |
| `code` | string | false | llm | |
| `command` | string | false | llm | |
| `session_id` | string | false | llm | |
| `session_reuse` | boolean | false | llm | |
| `code_interpreter_id` | string | false | llm | |

- `extra.python.source`: `tools/agentcube-code-interpreter.py`

## Provider implementation (`provider/agentcube.py`)

```python
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

class AgentcubeCodeInterpreterProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            """ IMPLEMENT YOUR VALIDATION HERE """
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
```

(OAuth helper methods are present only as comments.)

## Tool implementation (`tools/agentcube-code-interpreter.py`)

```python
from collections.abc import Generator
from typing import Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from agentcube import CodeInterpreterClient

class AgentcubeCodeInterpreterTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        result = self.execute(**tool_parameters)
        yield self.create_json_message(result)

    def execute(
        self,
        router_url=None,
        workload_manager_url=None,
        language="python",
        code_interpreter_id=None,
        session_id=None,
        code=None,
        command=None,
        session_reuse=False,
        **kwargs
    ): ...
```

## Plugin dependencies (`integrations/dify-plugin/requirements.txt`)

```
dify-plugin>=0.4.2,<0.5.0
agentcube-sdk>=0.0.10
```

## PCAP analyzer — application structure (`example/pcap-analyzer/`)

| File | Role |
|------|------|
| `pcap_analyzer.py` | FastAPI app, agents, sandbox runner, analysis orchestration, `uvicorn` entry |
| `requirements.txt` | FastAPI, uvicorn, LangChain / LangGraph stack, multipart, etc. |
| `Dockerfile` | `uv` base image, installs reqs, copies `sdk-python/agentcube` + `pcap_analyzer.py` |
| `deployment.yaml` | K8s Deployment + env for OpenAI-compatible API and AgentCube URLs |
| `README.md` | Documentation |

## FastAPI application (`pcap_analyzer.py`)

### Globals / config (selected)

| Name | Source | Default / value |
|------|--------|-----------------|
| `API_KEY` | `OPENAI_API_KEY` | required at startup |
| `API_BASE_URL` | `OPENAI_API_BASE` | `https://api.siliconflow.cn/v1` |
| `MODEL_NAME` | `OPENAI_MODEL` | `Qwen/QwQ-32B` |
| `CODEINTERPRETER_NAME` | env | `my-interpreter` |
| `SANDBOX_NAMESPACE` | env | `default` |
| `SANDBOX_WARMUP_SEC` | env | `5` |
| `SERVER_HOST` | constant | `0.0.0.0` |
| `SERVER_PORT` | constant | `8000` |
| `SERVER_RELOAD` | constant | `True` |

### Core classes / functions

```python
class SandboxRunner:
    def __init__(self, name: str = "my-interpreter", namespace: str = "default", warmup_sec: int = 5): ...
    def upload_file(self, local_path: str, remote_path: str) -> bool: ...
    def upload_bytes(self, data: bytes, remote_path: str) -> bool: ...
    def run(self, command: str) -> Dict[str, Any]: ...
    def stop(self): ...

def build_react_agent(llm, system_prompt: str): ...
def invoke_react_agent(agent, user_text: str) -> str: ...
def build_planner_agent(llm): ...
def build_reporter_agent(llm): ...

def _plan_script(agent, pcap_local_path: str) -> str: ...
def _repair_script(agent, prev_script: str, results: List[Dict[str, Any]]) -> str: ...
def _execute_once_in_runner(runner: SandboxRunner, pcap_local_path: str, script: str) -> List[Dict[str, Any]]: ...
def _analyze_with_retries(..., max_retries: int = 2) -> Dict[str, Any]: ...
def _report(agent, results: List[Dict[str, Any]]) -> str: ...

class AnalyzeResponse(BaseModel):
    script: str
    results: List[Dict[str, Any]]
    report: str

app = FastAPI(title="PCAP Analyzer — Env-Only Config")
```

### FastAPI endpoints

| Method | Path | Signature / behavior |
|--------|------|----------------------|
| (event) | startup | `on_startup()` → builds `ChatOpenAI`, `PLANNER`, `REPORTER`; fails if no API key |
| `POST` | `/analyze` | `async def analyze_endpoint(pcap_file: UploadFile = File(None), pcap_path: str = Form(None))` → `response_model=AnalyzeResponse` |

### Imports of note

```python
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
import uvicorn
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage
from agentcube.code_interpreter import CodeInterpreterClient
from agentcube.exceptions import CommandExecutionError
```

## Kubernetes deployment (`deployment.yaml`)

- `Deployment` `pcap-analyzer` in `namespace: default`
- Container `pcap-analyzer`, image `pcap-analyzer:latest`, `imagePullPolicy: IfNotPresent`
- Container port `8000` TCP
- Resources: requests `cpu: 200m`, `memory: 100Mi`; limits `cpu: 1`, `memory: 1Gi`
- Env: `OPENAI_API_KEY` from secret `pcap-analyzer-secrets` key `openai-api-key`; `OPENAI_API_BASE`, `OPENAI_MODEL`, `WORKLOAD_MANAGER_URL`, `ROUTER_URL`, `CODEINTERPRETER_NAME`, `SANDBOX_NAMESPACE`, `SANDBOX_WARMUP_SEC`
- Command: `["uv"]`, args: `["run", "pcap_analyzer.py"]`

## Dockerfile highlights

- Base: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`
- `uv venv` + `uv pip install -r requirements.txt`
- Copies `sdk-python/agentcube` → `./agentcube/`, `pcap_analyzer.py` → `./`
- `ENV PYTHONPATH="/app"`, exposes `8000`
- `CMD ["uv", "run", "pcap_analyzer.py"]`

## PCAP example Python dependencies (`example/pcap-analyzer/requirements.txt`)

Pinned packages include: `fastapi==0.120.0`, `uvicorn==0.38.0`, `langchain==1.0.2`, `langchain-classic==1.0.0`, `langchain-community==0.4.1`, `langchain-core==1.0.1`, `langchain-openai==1.0.1`, `langchain-text-splitters==1.0.0`, `langgraph==1.0.1`, `langgraph-checkpoint==3.0.0`, `langgraph-prebuilt==1.0.1`, `langgraph-sdk==0.2.9`, `langsmith==0.4.38`, `paramiko==4.0.0`, `python-multipart==0.0.20`

*(The Dockerfile vendors `agentcube` from the monorepo copy; it is not listed in this `requirements.txt`.)*
