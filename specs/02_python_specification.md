# AgentCube Python Specification

This document is derived from the Python sources under `/tmp/agentcube-ref` (CLI `cmd/cli/`, SDK `sdk-python/`, Dify plugin `integrations/dify-plugin/`, example `example/pcap-analyzer/`, plus project manifests). It is intended to support faithful reconstruction of behavior and layout.

---

## 1. agentcube-cli (`cmd/cli/`)

### 1.1 Package layout

| Path | Role |
|------|------|
| `agentcube/__init__.py` | Package version metadata; re-exports `app`, runtime classes |
| `agentcube/cli/main.py` | Typer application and commands |
| `agentcube/cli/__init__.py` | Package marker |
| `agentcube/models/pack_models.py` | `MetadataOptions` dataclass |
| `agentcube/runtime/` | `PackRuntime`, `BuildRuntime`, `PublishRuntime`, `InvokeRuntime`, `StatusRuntime` |
| `agentcube/services/` | `DockerService`, `MetadataService` (+ `AgentMetadata`), `KubernetesProvider`, `AgentCubeProvider` |
| `agentcube/operations/__init__.py` | Docstring-only module |
| `examples/hello-agent/main.py` | Sample HTTP agent |
| `examples/math-agent/main.py` | Sample LangChain/LangGraph agent |

**Setuptools packages** (`cmd/cli/pyproject.toml`): `agentcube`, `agentcube.cli`, `agentcube.runtime`, `agentcube.operations`, `agentcube.services`.

### 1.2 Entry point (console script)

| Script name | Target |
|-------------|--------|
| `kubectl-agentcube` | `agentcube.cli.main:app` |

The Typer app variable is named `app` with `name="agentcube"` in code.

### 1.3 Root `pyproject.toml` (monorepo)

- **Purpose:** IDE/ruff config; declares root project `agentcube` 0.1.0 with `requires-python = ">=3.10"`.
- **Ruff:** line length 120, target `py310`, lint `E,F,W`.

### 1.4 CLI dependencies (`cmd/cli/pyproject.toml`)

**Runtime (`dependencies`):**

| Dependency | Constraint |
|------------|------------|
| typer | `typer[all]>=0.9.0` |
| pydantic | `>=2.0.0` |
| pyyaml | `>=6.0` |
| httpx | `>=0.24.0` |
| docker | `>=6.0.0` |
| rich | `>=13.0.0` |
| packaging | `>=23.0` |
| importlib-resources | `>=6.0.0` |
| semver | `>=3.0.0` |

**Optional `k8s`:** `kubernetes>=28.0.0`  
**Optional `dev` / `test`:** pytest stack, ruff, mypy, pre-commit, httpx-mock, etc. (see file).

### 1.5 Third-party imports (behavioral dependencies)

Observed in CLI Python sources:

- **typer** — CLI framework  
- **rich** — `Console`, `Progress`, `SpinnerColumn`, `TextColumn`, `Table`  
- **pydantic** — `AgentMetadata` in `metadata_service.py`  
- **yaml** (`pyyaml`) — metadata load/save  
- **docker** — `DockerService`  
- **httpx** — async invoke in `InvokeRuntime`  
- **kubernetes** — `KubernetesProvider`, `AgentCubeProvider`  

Standard library used heavily: `logging`, `json`, `pathlib`, `typing`, `dataclasses`, `shlex`, `shutil`, `xml.etree.ElementTree`, `os`, `time`, `asyncio`, `warnings`.

### 1.6 Typer application and commands

**Global callback:** `main` on `@app.callback()`

| Option | Short | Type (Typer) | Default | Help |
|--------|-------|--------------|---------|------|
| `--version` | — | `Optional[bool]` | `None` | Show version and exit (`callback=version_callback`, `is_eager=True`) |
| `--verbose` | `-v` | `bool` | `False` | Enable verbose output |

**`version_callback(value: bool) -> None`** — if true, prints version from `agentcube.__version__` and raises `typer.Exit()`.

**`_handle_error(e: Exception, command_name: str, verbose: bool)`** — prints error; if `verbose`, traceback; raises `typer.Exit(1)`.

---

#### Command: `pack`

**Callback:** `pack(...) -> None`

| Option | Short | Type | Default | Help |
|--------|-------|------|---------|------|
| `--workspace` | `-f` | `str` | `"."` | Path to the agent workspace directory |
| `--agent-name` | — | `Optional[str]` | `None` | Override the agent name |
| `--language` | — | `Optional[str]` | `None` | Programming language (python, java) |
| `--entrypoint` | — | `Optional[str]` | `None` | Override the entrypoint command |
| `--port` | — | `Optional[int]` | `None` | Port to expose in the Dockerfile |
| `--build-mode` | — | `Optional[str]` | `None` | Build strategy: local or cloud |
| `--description` | — | `Optional[str]` | `None` | Agent description |
| `--output` | — | `Optional[str]` | `None` | Output path for packaged workspace |
| `--verbose` | — | `bool` | `False` | Enable detailed logging |

**Implementation:** Instantiates `PackRuntime(verbose=verbose)`, builds `MetadataOptions`, filters Nones, calls `runtime.pack(Path(workspace).resolve(), **options)` (adds `output` key when set).

---

#### Command: `build`

**Callback:** `build(...) -> None`

| Option | Short | Type | Default | Help |
|--------|-------|------|---------|------|
| `--workspace` | `-f` | `str` | `"."` | Path to the agent workspace directory |
| `--proxy` | `-p` | `Optional[str]` | `None` | Custom proxy URL for dependency resolution |
| `--cloud-provider` | — | `Optional[str]` | `None` | Cloud provider name (e.g., huawei) |
| `--output` | — | `Optional[str]` | `None` | Output path for build artifacts |
| `--verbose` | — | `bool` | `False` | Enable detailed logging |

**Implementation:** `BuildRuntime.build(workspace_path, **filtered_options)` with keys `proxy`, `cloud_provider`, `output`.

---

#### Command: `publish`

**Callback:** `publish(...) -> None`

| Option | Type | Default | Help |
|--------|------|---------|------|
| `-f` / `--workspace` | `str` | `"."` | Path to the agent workspace directory |
| `--version` | `Optional[str]` | `None` | Semantic version string (e.g., v1.0.0) |
| `--image-url` | `Optional[str]` | `None` | Image repository URL (required in local build mode) |
| `--image-username` | `Optional[str]` | `None` | Username for image repository |
| `--image-password` | `Optional[str]` | `None` | Password for image repository |
| `--description` | `Optional[str]` | `None` | Agent description |
| `--region` | `Optional[str]` | `None` | Deployment region |
| `--cloud-provider` | `Optional[str]` | `None` | Cloud provider name (e.g., huawei) |
| `--provider` | `str` | `"agentcube"` | Target provider: `agentcube` (AgentRuntime CR) or `k8s` (Deployment/Service) |
| `--node-port` | `Optional[int]` | `None` | Specific NodePort (30000-32767) for K8s deployment |
| `--replicas` | `Optional[int]` | `None` | Number of replicas for K8s deployment (default: 1) |
| `--namespace` | `Optional[str]` | `None` | The namespace for the deployment |
| `--verbose` | `bool` | `False` | Enable detailed logging |

**Implementation:** `PublishRuntime(verbose=verbose, provider=provider).publish(...)`.

---

#### Command: `invoke`

**Callback:** `invoke(...) -> None`

| Option | Type | Default | Help |
|--------|------|---------|------|
| `-f` / `--workspace` | `str` | `"."` | Path to the agent workspace directory |
| `--payload` | `str` | `"{}"` | JSON-formatted input passed to the agent |
| `--header` | `Optional[List[str]]` | `None` | Custom HTTP headers (`key:value`), repeatable |
| `--provider` | `str` | `"agentcube"` | `agentcube` or `k8s` |
| `--verbose` | `bool` | `False` | Enable detailed logging |

**Implementation:** Parses JSON payload; parses headers; `InvokeRuntime(verbose, provider).invoke(workspace_path, payload_data, headers)`.

---

#### Command: `status`

**Callback:** `status(...) -> None`

| Option | Type | Default | Help |
|--------|------|---------|------|
| `-f` / `--workspace` | `str` | `"."` | Path to the agent workspace directory |
| `--provider` | `str` | `"agentcube"` | `agentcube` or `k8s` |
| `--verbose` | `bool` | `False` | Enable detailed logging |

**Implementation:** `StatusRuntime(verbose, provider).get_status(workspace_path, provider=provider)`; renders `rich.table.Table`.

---

### 1.7 Runtime classes

#### `PackRuntime` (`agentcube/runtime/pack_runtime.py`)

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, verbose: bool = False) -> None` | Sets `verbose`, `MetadataService`; optional DEBUG logging |
| `pack` | `(self, workspace_path: Path, **options: Any) -> Dict[str, Any]` | Package agent workspace; returns paths and metadata fields |
| `_validate_workspace_structure` | `(self, workspace_path: Path) -> None` | Exists and is directory |
| `_load_or_create_metadata` | `(self, workspace_path: Path, options: Dict[str, Any]) -> AgentMetadata` | Load YAML or create from `MetadataOptions` |
| `_apply_option_overrides` | `(self, metadata: AgentMetadata, options: Dict[str, Any]) -> AgentMetadata` | Merge non-None overrides |
| `_validate_language_compatibility` | `(self, workspace_path: Path, metadata: AgentMetadata) -> None` | python vs java checks |
| `_validate_python_compatibility` | `(self, workspace_path: Path) -> None` | Requires `*.py`; warns if no `requirements.txt` |
| `_validate_java_compatibility` | `(self, workspace_path: Path) -> None` | Requires `pom.xml` |
| `_process_dependencies` | `(self, workspace_path: Path, metadata: AgentMetadata) -> None` | Language-specific |
| `_process_python_dependencies` | `(self, workspace_path: Path) -> None` | Reads `requirements.txt` if present |
| `_process_java_dependencies` | `(self, workspace_path: Path) -> None` | Log-only for Maven |
| `_generate_dockerfile` | `(self, workspace_path: Path, metadata: AgentMetadata) -> Optional[Path]` | Skip if Dockerfile exists |
| `_generate_python_dockerfile` | `(self, metadata: AgentMetadata) -> str` | Dockerfile template string |
| `_generate_java_dockerfile` | `(self, metadata: AgentMetadata) -> str` | Multi-stage Maven + JRE |
| `_update_pack_metadata` | `(self, workspace_path: Path, metadata: AgentMetadata, dockerfile_path: Optional[Path]) -> None` | Sets `has_dockerfile` |
| `_prepare_output_path` | `(self, workspace_path: Path, output_path: Optional[str]) -> Path` | Optional copytree to output |
| `_infer_entrypoint` | `(self, workspace_path: Path, language: str) -> str` | python: `main.py`/`app.py`/`run.py` or default `python main.py`; java: `mvn spring-boot:run` |

---

#### `BuildRuntime` (`agentcube/runtime/build_runtime.py`)

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, verbose: bool = False) -> None` | `MetadataService`, `DockerService` |
| `build` | `(self, workspace_path: Path, **options: Any) -> Dict[str, Any]` | Validates, increments version, local or cloud build; reverts version on failure |
| `_increment_version` | `(self, workspace_path: Path, metadata) -> Any` | Patch bump in `X.Y.Z`; updates metadata |
| `_validate_build_prerequisites` | `(self, workspace_path: Path) -> None` | Dockerfile must exist |
| `_build_local` | `(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> Dict[str, Any]` | Docker build with optional proxy buildargs |
| `_build_cloud` | `(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> Dict[str, Any]` | TODO; delegates to `_build_local` |
| `_update_build_metadata` | `(self, workspace_path: Path, metadata, build_result: Dict[str, str], tag: str = "latest") -> None` | Writes `image` block |

---

#### `PublishRuntime` (`agentcube/runtime/publish_runtime.py`)

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, verbose: bool = False, provider: str = "agentcube") -> None` | Services/providers lazily used |
| `publish` | `(self, workspace_path: Path, **options: Any) -> Dict[str, Any]` | Routes to AgentRuntime CR or standard K8s |
| `_publish_cr_to_k8s` | `(self, workspace_path: Path, metadata, **options: Any) -> Dict[str, Any]` | `AgentCubeProvider.deploy_agent_runtime` |
| `_publish_k8s` | `(self, workspace_path: Path, metadata, **options: Any) -> Dict[str, Any]` | `KubernetesProvider.deploy_agent` + readiness wait |
| `_prepare_image_for_publishing` | `(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> str` | local vs cloud image resolution |
| `_prepare_local_image` | `(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> str` | Push to registry or require `--image-url` |
| `_prepare_cloud_image` | `(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> str` | Uses `metadata.image.repository_url` |
| `_update_publish_metadata` | `(self, workspace_path: Path, agent_info: Dict[str, Any]) -> None` | agent_id, endpoint, version |

---

#### `InvokeRuntime` (`agentcube/runtime/invoke_runtime.py`)

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, verbose: bool = False, provider: str = "agentcube") -> None` | Initializes `AgentCubeProvider` or `KubernetesProvider` per provider |
| `invoke` | `(self, workspace_path: Path, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any` | Loads metadata; may rewrite URL for AgentRuntime; adds `X-Agentcube-Session-Id`; runs async HTTP |
| `_validate_invoke_prerequisites` | `(self, workspace_path: Path) -> Tuple[Any, str, str]` | metadata, agent_id, endpoint |
| `_invoke_agent_via_agentcube` | `async (self, agent_id: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]], endpoint: str, workspace_path: Path) -> Any` | Dispatches HTTP if `endpoint.startswith("http")` |
| `_direct_http_invocation` | `async (self, endpoint: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]], workspace_path: Path) -> Dict[str, Any]` | `httpx.AsyncClient` POST; persists session id from response header |

**Note:** `_invoke_agent_via_agentcube` only assigns `response` when `endpoint.startswith("http")`; other schemes would leave `response` undefined before return (implementation gap).

---

#### `StatusRuntime` (`agentcube/runtime/status_runtime.py`)

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, verbose: bool = False, provider: str = "agentcube") -> None` | Same provider init pattern as invoke |
| `get_status` | `(self, workspace_path: Path, provider: Optional[str] = None) -> Dict[str, Any]` | not_published / CR status / standard K8s status |
| `_get_k8s_status` | `(self, metadata) -> Dict[str, Any]` | `KubernetesProvider.get_agent_status` |
| `_get_cr_k8s_status` | `(self, metadata) -> Dict[str, Any]` | `AgentCubeProvider.get_agent_runtime` |

---

### 1.8 Service classes

#### `DockerService` (`agentcube/services/docker_service.py`)

| Member | Signature | Docstring / behavior |
|--------|-----------|----------------------|
| `__init__` | `(self, verbose: bool = False) -> None` | `docker.from_env()`, ping; sets `client` or `None` on failure |
| `check_docker_available` | `(self) -> bool` | Ping daemon |
| `build_image` | `(self, dockerfile_path: Path, context_path: Path, image_name: str, tag: str = "latest", build_args: Optional[Dict[str, str]] = None) -> Dict[str, str]` | Returns image_name, id, size, build_time |
| `get_image_info` | `(self, image_name: str) -> Dict[str, str]` | Delegates to `_get_image_info` |
| `_get_image_info` | `(self, image_name: str) -> Dict[str, str]` | id + formatted size |
| `_format_size` | `(self, size_bytes: int) -> str` | Human-readable |
| `push_image` | `(self, image_name: str, registry_url: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None) -> Dict[str, str]` | login, tag, push stream |
| `_docker_login_sdk` | `(self, registry: Optional[str], username: str, password: str) -> None` | |
| `_tag_image_sdk` | `(self, source_image: str, target_image: str) -> None` | |
| `remove_image` | `(self, image_name: str) -> bool` | force remove |

---

#### `MetadataService` (`agentcube/services/metadata_service.py`)

**Pydantic model: `AgentMetadata(BaseModel)`**

| Field | Type (as in source) | Default | `Field` description |
|-------|---------------------|---------|---------------------|
| `agent_name` | `str` | (required) | Unique name identifying the agent |
| `description` | `Optional[str]` | `None` | Human-readable summary |
| `language` | `str` | `"python"` | Programming language used |
| `entrypoint` | `str` | (required) | Command to launch the agent |
| `port` | `int` | `8080` | Port exposed by the agent runtime |
| `build_mode` | `str` | `"local"` | Build strategy: local or cloud |
| `region` | `Optional[str]` | `None` | Deployment region |
| `version` | `Optional[str]` | `None` | Semantic version for publishing |
| `image` | `Optional[Dict[str, Any]]` | `None` | Container image information |
| `auth` | `Optional[Dict[str, Any]]` | `None` | Authentication configuration |
| `requirements_file` | `Optional[str]` | `"requirements.txt"` | Python dependency file |
| `registry_url` | `Optional[str]` | `""` | Registry URL for image publishing |
| `registry_username` | `Optional[str]` | `""` | Registry username |
| `registry_password` | `Optional[str]` | `""` | Registry password |
| `agent_endpoint` | `Optional[str]` | `None` | Agent endpoint URL |
| `workload_manager_url` | `Optional[str]` | `None` | URL for the Workload Manager |
| `router_url` | `Optional[str]` | `None` | URL for the Router |
| `readiness_probe_path` | `Optional[str]` | `None` | Path for the readiness probe |
| `readiness_probe_port` | `Optional[int]` | `None` | Port for the readiness probe |
| `agent_id` | `Optional[str]` | `None` | Agent ID assigned by AgentCube |
| `session_id` | `Optional[str]` | `None` | Session ID for the agent |
| `k8s_deployment` | `Optional[Dict[str, Any]]` | `None` | Kubernetes deployment information |

**Validators:** `language` ∈ {python, java}; `build_mode` ∈ {local, cloud}; `port` in 1–65535.

| `MetadataService` method | Signature | Docstring summary |
|-------------------------|-----------|-------------------|
| `__init__` | `(self, verbose: bool = False) -> None` | |
| `load_metadata` | `(self, workspace_path: Path) -> AgentMetadata` | `agent_metadata.yaml`, else `agent.yaml` / `metadata.yaml` |
| `save_metadata` | `(self, workspace_path: Path, metadata: AgentMetadata) -> None` | YAML dump `exclude_none=True` |
| `update_metadata` | `(self, workspace_path: Path, updates: Dict[str, Any]) -> AgentMetadata` | merge and save |
| `validate_workspace` | `(self, workspace_path: Path) -> bool` | structure + language-specific |
| `_validate_python_workspace` | `(self, workspace_path: Path, metadata: AgentMetadata) -> None` | entrypoint file + requirements |
| `_validate_java_workspace` | `(self, workspace_path: Path, metadata: AgentMetadata) -> None` | `pom.xml` + `src/main/java` |

---

#### `KubernetesProvider` (`agentcube/services/k8s_provider.py`)

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, namespace: str = "default", verbose: bool = False, kubeconfig: Optional[str] = None) -> None` | in-cluster or kubeconfig; CoreV1 + AppsV1 APIs |
| `_ensure_namespace` | `(self) -> None` | Create namespace if missing |
| `deploy_agent` | `(self, agent_name: str, image_url: str, port: int, entrypoint: Optional[str] = None, replicas: int = 1, node_port: Optional[int] = None, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]` | Deployment + NodePort Service |
| `_create_deployment` | `(self, name: str, image_url: str, port: int, entrypoint: Optional[str], replicas: int, env_vars: Optional[Dict[str, str]]) -> Dict[str, Any]` | create or patch |
| `_create_service` | `(self, name: str, port: int, node_port: Optional[int]) -> Dict[str, Any]` | NodePort |
| `wait_for_deployment_ready` | `(self, name: str, timeout: int = 120) -> None` | Poll replicas |
| `get_agent_status` | `(self, agent_name: str) -> Dict[str, Any]` | deployment + service + pods |
| `delete_agent` | `(self, agent_name: str) -> Dict[str, Any]` | delete deployment and service |
| `_sanitize_name` | `(self, name: str) -> str` | DNS-1123 subset, max 63 |

---

#### `AgentCubeProvider` (`agentcube/services/agentcube_provider.py`)

**AgentRuntime CR:** `group=runtime.agentcube.volcano.sh`, `version=v1alpha1`, `plural=agentruntimes`.

| Member | Signature | Docstring summary |
|--------|-----------|-------------------|
| `__init__` | `(self, namespace: str = "default", verbose: bool = False, kubeconfig: Optional[str] = None) -> None` | CoreV1 + CustomObjectsApi |
| `_ensure_namespace` | `(self) -> None` | Same pattern as K8s provider |
| `deploy_agent_runtime` | `(self, agent_name: str, image_url: str, port: int, entrypoint: Optional[str] = None, env_vars: Optional[Dict[str, str]] = None, workload_manager_url: Optional[str] = None, router_url: Optional[str] = None, readiness_probe_path: Optional[str] = None, readiness_probe_port: Optional[int] = None,) -> Dict[str, Any]` | create/patch CR; injects WORKLOAD_MANAGER_URL / ROUTER_URL |
| `_sanitize_name` | `(self, name: str) -> str` | Same as K8s provider |
| `get_agent_runtime` | `(self, name: str, namespace: str) -> Optional[Dict[str, Any]]` | get_namespaced_custom_object; None if 404 |

---

### 1.9 Data models (`agentcube/models/pack_models.py`)

**`MetadataOptions` — `@dataclass` (not Pydantic)**

| Field | Type | Default |
|-------|------|---------|
| `agent_name` | `Optional[str]` | `None` |
| `language` | `Optional[str]` | `'python'` |
| `entrypoint` | `Optional[str]` | `None` |
| `port` | `Optional[int]` | `8080` |
| `build_mode` | `Optional[str]` | `'local'` |
| `requirements_file` | `Optional[str]` | `None` |
| `description` | `Optional[str]` | `None` |
| `workload_manager_url` | `Optional[str]` | `""` |
| `router_url` | `Optional[str]` | `""` |
| `readiness_probe_path` | `Optional[str]` | `""` |
| `readiness_probe_port` | `Optional[int]` | `8080` |
| `registry_url` | `Optional[str]` | `""` |
| `registry_username` | `Optional[str]` | `""` |
| `registry_password` | `Optional[str]` | `""` |
| `agent_endpoint` | `Optional[str]` | `""` |

| Method | Signature |
|--------|-----------|
| `from_options` | `@classmethod def from_options(cls, options: Dict[str, Any]) -> "MetadataOptions"` |

---

### 1.10 `agentcube` package public surface (`agentcube/__init__.py`)

- `__version__ = "0.1.0"`
- `__all__`: `app`, `PackRuntime`, `BuildRuntime`, `PublishRuntime`, `InvokeRuntime`

(`StatusRuntime` and `MetadataOptions` are exported from `agentcube.runtime.__init__` but not from top-level `agentcube`.)

---

### 1.11 CLI examples (supplementary)

**`examples/hello-agent/main.py`:** `HTTPServer` + `HelloAgentHandler`; uses `CodeInterpreterClient` from `agentcube` on `/runcmd` and POST `/`. Dependencies file lists `agentcube_sdk` (naming as published).

**`examples/math-agent/main.py`:** LangChain `create_agent`, `init_chat_model`, tool `run_python_code` wrapping per-call `CodeInterpreterClient()`. Env: `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_MODEL`. Requires `python-dotenv`, langchain stack, `agentcube_sdk`.

---

## 2. agentcube-sdk (`sdk-python/`)

### 2.1 Package layout

| Path | Role |
|------|------|
| `agentcube/__init__.py` | Exports `CodeInterpreterClient`, `AgentRuntimeClient` |
| `agentcube/code_interpreter.py` | High-level Code Interpreter API |
| `agentcube/agent_runtime.py` | Agent runtime invoke client |
| `agentcube/exceptions.py` | Exception types |
| `agentcube/clients/control_plane.py` | Workload Manager HTTP client |
| `agentcube/clients/code_interpreter_data_plane.py` | Router → PicoD client |
| `agentcube/clients/agent_runtime_data_plane.py` | Agent runtime invocations |
| `agentcube/utils/http.py` | `create_session` |
| `agentcube/utils/utils.py` | `read_token_from_file` |
| `agentcube/utils/log.py` | `get_logger` |
| `tests/` | `test_code_interpreter.py`, `test_agent_runtime.py` |
| `examples/` | `basic_usage.py`, `agent_runtime_usage.py` |
| `scripts/e2e_picod_test.py` | E2E JWT simulation (uses PyJWT + cryptography) |

### 2.2 `pyproject.toml` dependencies

| Dependency | Constraint |
|------------|------------|
| requests | (no bound) |
| PyJWT | `>=2.0.0` |
| cryptography | (no bound) |

**Note:** Library code paths use `requests` only; `PyJWT`/`cryptography` appear in `scripts/e2e_picod_test.py`, not in the `agentcube` package modules reviewed.

`requirements.txt` mirrors: `requests`, `PyJWT>=2.0.0`, `cryptography`.

### 2.3 Public API (`agentcube/__init__.py`)

```python
__all__ = ["CodeInterpreterClient", "AgentRuntimeClient"]
```

`agentcube/clients/__init__.py` additionally documents: `ControlPlaneClient`, `CodeInterpreterDataPlaneClient`, `AgentRuntimeDataPlaneClient`.

---

### 2.4 `CodeInterpreterClient` (`agentcube/code_interpreter.py`)

| Member | Signature | Returns / notes |
|--------|-----------|-----------------|
| `__init__` | `(self, name: str = "my-interpreter", namespace: str = "default", ttl: int = 3600, workload_manager_url: Optional[str] = None, router_url: Optional[str] = None, auth_token: Optional[str] = None, verbose: bool = False, session_id: Optional[str] = None,)` | Raises `ValueError` if no `router_url` / `ROUTER_URL`; creates session via CP unless `session_id` |
| `_init_data_plane` | `(self)` | Constructs `CodeInterpreterDataPlaneClient` |
| `__enter__` | `(self)` | `return self` |
| `__exit__` | `(self, exc_type, exc_val, exc_tb)` | calls `stop()` |
| `stop` | `(self)` | closes DP, deletes session via CP, closes CP |
| `execute_command` | `(self, command: str, timeout: Optional[float] = None) -> str` | |
| `run_code` | `(self, language: str, code: str, timeout: Optional[float] = None) -> str` | |
| `write_file` | `(self, content: str, remote_path: str)` | |
| `upload_file` | `(self, local_path: str, remote_path: str)` | |
| `download_file` | `(self, remote_path: str, local_path: str)` | |
| `list_files` | `(self, path: str = ".")` | Returns list from DP |

**Instance attributes:** `name`, `namespace`, `ttl`, `verbose`, `logger`, `cp_client`, `router_url`, `session_id`, `dp_client`.

---

### 2.5 `AgentRuntimeClient` (`agentcube/agent_runtime.py`)

| Member | Signature | Returns |
|--------|-----------|---------|
| `__init__` | `(self, agent_name: str, namespace: str = "default", router_url: Optional[str] = None, verbose: bool = False, session_id: Optional[str] = None, timeout: int = 120, connect_timeout: float = 5.0,)` | Bootstraps `session_id` via DP GET if missing |
| `__enter__` / `__exit__` | | `close()` on exit |
| `invoke` | `(self, payload: Dict[str, Any], timeout: Optional[float] = None) -> Any` | JSON or text on decode error |
| `close` | `(self) -> None` | Closes `dp_client` |

---

### 2.6 `ControlPlaneClient` (`agentcube/clients/control_plane.py`)

**Base URL:** `workload_manager_url` or env `WORKLOAD_MANAGER_URL` (required).

**Default headers:** `Content-Type: application/json`; `Authorization: Bearer <token>` if token from arg or `/var/run/secrets/kubernetes.io/serviceaccount/token` (via `read_token_from_file`).

| Member | Signature |
|--------|-----------|
| `__init__` | `(self, workload_manager_url: Optional[str] = None, auth_token: Optional[str] = None, timeout: int = 120, connect_timeout: float = 5.0, pool_connections: int = 10, pool_maxsize: int = 10,)` |
| `create_session` | `(self, name: str = "my-interpreter", namespace: str = "default", metadata: Optional[Dict[str, Any]] = None, ttl: int = 3600,) -> str` |
| `delete_session` | `(self, session_id: str) -> bool` |
| `close` | `(self)` |

**HTTP:**

| Method | Path | Body / notes |
|--------|------|--------------|
| POST | `{base_url}/v1/code-interpreter` | JSON `name`, `namespace`, `ttl`, `metadata`; response must include `sessionId` |
| DELETE | `{base_url}/v1/code-interpreter/sessions/{session_id}` | 404 treated as success |

Timeouts: `(connect_timeout, timeout)` on each request.

---

### 2.7 `CodeInterpreterDataPlaneClient` (`agentcube/clients/code_interpreter_data_plane.py`)

**Base URL construction:**

- If `base_url` provided: use as-is.
- Else: `urljoin(router_url, f"/v1/namespaces/{namespace}/code-interpreters/{cr_name}/invocations/")`

**Session header on pooled session:** `x-agentcube-session-id: <session_id>`  
**Multipart upload** also sets `x-agentcube-session-id` on the per-request headers.

| Member | Signature |
|--------|-----------|
| `__init__` | `(self, session_id: str, router_url: Optional[str] = None, namespace: Optional[str] = None, cr_name: Optional[str] = None, base_url: Optional[str] = None, timeout: int = 120, connect_timeout: float = 5.0, pool_connections: int = 10, pool_maxsize: int = 10,)` |
| `_request` | `(self, method: str, endpoint: str, body: Optional[bytes] = None, **kwargs) -> requests.Response` | Sets JSON content-type when body present; default timeout tuple |
| `execute_command` | `(self, command: Union[str, List[str]], timeout: Optional[float] = None) -> str` | POST `api/execute`; raises `CommandExecutionError` if `exit_code != 0` |
| `run_code` | `(self, language: str, code: str, timeout: Optional[float] = None) -> str` | python/bash via temp script files |
| `write_file` | `(self, content: str, remote_path: str) -> None` | POST `api/files` base64 JSON |
| `upload_file` | `(self, local_path: str, remote_path: str) -> None` | POST multipart `api/files` |
| `download_file` | `(self, remote_path: str, local_path: str) -> None` | GET `api/files/{clean_path}` stream |
| `list_files` | `(self, path: str = ".") -> Any` | GET `api/files?path=` → `resp.json().get("files", [])` |
| `close` | `(self)` | `session.close()` |

**Relative endpoints (appended to `base_url`):** `api/execute`, `api/files`, `api/files/{path}`.

---

### 2.8 `AgentRuntimeDataPlaneClient` (`agentcube/clients/agent_runtime_data_plane.py`)

**Class constant:** `SESSION_HEADER = "x-agentcube-session-id"`

**Base URL:** `urljoin(router_url, f"/v1/namespaces/{namespace}/agent-runtimes/{agent_name}/invocations/")`

| Member | Signature |
|--------|-----------|
| `__init__` | `(self, router_url: str, namespace: str, agent_name: str, timeout: int = 120, connect_timeout: float = 5.0, pool_connections: int = 10, pool_maxsize: int = 10,)` |
| `bootstrap_session_id` | `(self) -> str` | GET `base_url`; reads `x-agentcube-session-id` header |
| `invoke` | `(self, session_id: str, payload: Dict[str, Any], timeout: Optional[float] = None,) -> requests.Response` | POST `base_url` with session header + `Content-Type: application/json` |
| `close` | `(self) -> None` | |

---

### 2.9 `create_session` (`agentcube/utils/http.py`)

```python
def create_session(
    pool_connections: int = 10,
    pool_maxsize: int = 10,
) -> requests.Session
```

Mounts `HTTPAdapter` for `http://` and `https://`.

---

### 2.10 Configuration (environment + constructor)

| Variable / parameter | Used by | Semantics |
|---------------------|---------|-----------|
| `ROUTER_URL` | `CodeInterpreterClient`, `AgentRuntimeClient` | Required if `router_url` arg omitted |
| `WORKLOAD_MANAGER_URL` | `ControlPlaneClient` | Required if `workload_manager_url` omitted |
| K8s SA token file | `ControlPlaneClient` | Default path `/var/run/secrets/kubernetes.io/serviceaccount/token` |
| `WORKLOAD_MANAGER_URL` / `ROUTER_URL` | `AgentCubeProvider` (CLI) | Optional env fallback when deploying CR |

---

### 2.11 Exception hierarchy (`agentcube/exceptions.py`)

| Class | Bases | Fields / message |
|-------|-------|------------------|
| `AgentCubeError` | `Exception` | Base |
| `CommandExecutionError` | `AgentCubeError` | `exit_code`, `stderr`, `command`; message `Command failed (exit {exit_code}): {stderr}` |
| `SessionError` | `AgentCubeError` | Placeholder |
| `DataPlaneError` | `AgentCubeError` | Placeholder |

---

### 2.12 Tests (summary)

- **`tests/test_code_interpreter.py`:** mocks CP/DP; session create vs reuse; context manager calls `stop`.
- **`tests/test_agent_runtime.py`:** mocks DP; bootstrap vs reuse; `invoke` JSON vs text fallback.

---

## 3. Dify plugin (`integrations/dify-plugin/`)

### 3.1 Runner entrypoint

**`main.py`**

```python
from dify_plugin import Plugin, DifyPluginEnv
plugin = Plugin(DifyPluginEnv(MAX_REQUEST_TIMEOUT=120))
if __name__ == '__main__':
    plugin.run()
```

### 3.2 Manifest (`manifest.yaml`)

| Key | Value (summary) |
|-----|-----------------|
| `version` | `0.0.2` |
| `type` | `plugin` |
| `author` | `volcano-sh` |
| `name` | `agentcube` |
| `plugins.tools` | `- provider/agentcube.yaml` |
| `meta.runner` | `language: python`, `version: "3.12"`, `entrypoint: main` |
| `resource` | memory 256MiB; permissions for tool, endpoint, app, storage |

### 3.3 Provider (`provider/agentcube.yaml` + `provider/agentcube.py`)

**YAML:** registers tools list `tools/agentcube-code-interpreter.yaml`; Python source `provider/agentcube.py`.

**Python:** `class AgentcubeCodeInterpreterProvider(ToolProvider)` with `_validate_credentials(self, credentials: dict[str, Any]) -> None` — empty try block (stub validation). OAuth helpers commented in source.

### 3.4 Tool (`tools/agentcube-code-interpreter.yaml` + `.py`)

**YAML parameters:**

| name | type | required | notes |
|------|------|----------|-------|
| `router_url` | string | yes | form |
| `workload_manager_url` | string | yes | form |
| `language` | select | no | python / javascript / typescript |
| `code` | string | no | llm form |
| `command` | string | no | llm form |
| `session_id` | string | no | llm form |
| `session_reuse` | boolean | no | llm form |
| `code_interpreter_id` | string | no | llm form |

**Python:** `class AgentcubeCodeInterpreterTool(Tool)`

- `_invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]` → `yield self.create_json_message(self.execute(**tool_parameters))`
- `execute(self, router_url=None, workload_manager_url=None, language="python", code_interpreter_id=None, session_id=None, code=None, command=None, session_reuse=False, **kwargs)`  
  - Requires both URLs; builds `CodeInterpreterClient(**client_kwargs)` with optional `name` from `code_interpreter_id`, `session_id`  
  - Runs `execute_command` / `run_code` as provided; requires at least one of `command` or `code`  
  - Unless `session_reuse`, calls `ci_client.stop()` in `finally`

### 3.5 Plugin dependencies (`integrations/dify-plugin/requirements.txt`)

```
dify-plugin>=0.4.2,<0.5.0
agentcube-sdk>=0.0.10
```

---

## 4. Example: PCAP analyzer (`example/pcap-analyzer/`)

### 4.1 Structure

Single module `pcap_analyzer.py` (run as `uvicorn.run("pcap_analyzer:app", ...)`).

### 4.2 Dependencies (`requirements.txt`)

Pinned stack: `fastapi`, `uvicorn`, `langchain*`, `langgraph*`, `langsmith`, `paramiko`, `python-multipart`, etc. (see file). Imports **`CodeInterpreterClient`** and **`CommandExecutionError`** from `agentcube` (SDK).

### 4.3 Key functionality

- **FastAPI** app `PCAP Analyzer — Env-Only Config`.
- **Startup:** requires `OPENAI_API_KEY`; builds `ChatOpenAI` with `OPENAI_API_BASE`, `OPENAI_MODEL`; two LangGraph ReAct agents (planner + reporter) with **no tools** — plain LLM JSON/Markdown generation.
- **`SandboxRunner`:** wraps `CodeInterpreterClient(name, namespace, verbose=True)`; optional warmup sleep; `upload_file`, `upload_bytes`, `run` (maps `CommandExecutionError` to result dict), `stop`.
- **Pipeline:** POST `/analyze` with `pcap_file` (upload) or `pcap_path` (local path) → planner produces bash script → upload PCAP to `/workspace/pocket.pcap` and script to `/workspace/plan.sh` → `chmod +x` and `/bin/sh plan.sh` with retries (`PLANNER_MAX_RETRIES`) → reporter produces Markdown.
- **Response model:** `AnalyzeResponse(BaseModel)` with `script: str`, `results: List[Dict[str, Any]]`, `report: str`.
- **Env knobs:** `CODEINTERPRETER_NAME`, `SANDBOX_NAMESPACE`, `SANDBOX_WARMUP_SEC`, `LOG_LEVEL`, `LOG_SEP_CHAR`, `LOG_SEP_WIDTH`, `DEBUG_SAVE_DIR`, `PLANNER_MAX_RETRIES`, OpenAI-related vars.

---

## 5. Cross-package naming note

The CLI and the SDK both use the **top-level package name `agentcube`**. In deployment, the CLI is `agentcube-cli` (console script `kubectl-agentcube`); the SDK is `agentcube-sdk` on PyPI but imports as `agentcube`. Example and Dify code depend on the SDK distribution.

---

## 6. Source file inventory (Python)

**CLI (`cmd/cli/`, recursive):** 18 `.py` files including `examples/hello-agent/main.py`, `examples/math-agent/main.py`, and package modules listed in §1.1.

**SDK (`sdk-python/`, recursive):** 17 `.py` files (including `tests/`, `examples/`, `scripts/e2e_picod_test.py`).

**Dify:** `main.py`, `provider/agentcube.py`, `tools/agentcube-code-interpreter.py`.

**Example:** `example/pcap-analyzer/pcap_analyzer.py`.

**Config files read:** root `/tmp/agentcube-ref/pyproject.toml`; `cmd/cli/pyproject.toml`; `sdk-python/pyproject.toml`; all `requirements.txt` paths listed in this spec.
