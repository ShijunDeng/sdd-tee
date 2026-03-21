# AgentCube CLI (cli-toolkit) — Design

Source root: `/tmp/agentcube-ref/cmd/cli/`.

## Package layout (every module path and role)

| Path | Role |
|------|------|
| `pyproject.toml` | Project metadata, dependencies, console script mapping |
| `agentcube/__init__.py` | Package version `__version__`, exports `app`, runtimes |
| `agentcube/cli/__init__.py` | CLI subpackage marker |
| `agentcube/cli/main.py` | Typer `app`, all commands, `_handle_error`, `version_callback` |
| `agentcube/models/pack_models.py` | `MetadataOptions` dataclass |
| `agentcube/runtime/__init__.py` | Re-exports runtimes + `MetadataOptions` |
| `agentcube/runtime/pack_runtime.py` | `PackRuntime` |
| `agentcube/runtime/build_runtime.py` | `BuildRuntime` |
| `agentcube/runtime/publish_runtime.py` | `PublishRuntime` |
| `agentcube/runtime/invoke_runtime.py` | `InvokeRuntime` |
| `agentcube/runtime/status_runtime.py` | `StatusRuntime` |
| `agentcube/services/__init__.py` | Services package docstring |
| `agentcube/services/metadata_service.py` | `AgentMetadata`, `MetadataService` |
| `agentcube/services/docker_service.py` | `DockerService` |
| `agentcube/services/k8s_provider.py` | `KubernetesProvider` |
| `agentcube/services/agentcube_provider.py` | `AgentCubeProvider` |
| `agentcube/operations/__init__.py` | Placeholder module docstring (no symbols) |
| `examples/hello-agent/main.py` | Example agent |
| `examples/math-agent/main.py` | Example agent |

**Setuptools packages** (from `pyproject.toml` `[tool.setuptools]`):  
`agentcube`, `agentcube.cli`, `agentcube.runtime`, `agentcube.operations`, `agentcube.services`  
*(Note: `agentcube.models` is not listed in `[tool.setuptools] packages` but is imported; packaging may rely on setuptools discovery for subpackages — reconstruct imports from source as above.)*

## Console script entry point

```toml
[project.scripts]
kubectl-agentcube = "agentcube.cli.main:app"
```

Typer app object: `app = typer.Typer(name="agentcube", help="...", no_args_is_help=True, rich_markup_mode="rich", add_completion=False)`.

## Typer — root callback

```python
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", help="Show version and exit",
        callback=version_callback, is_eager=True,
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
) -> None:
    """AgentCube CLI - A developer tool for AI agent lifecycle management."""
```

## Typer — `pack`

```python
def pack(
    workspace: str = typer.Option(".", "-f", "--workspace", help="Path to the agent workspace directory", show_default=True),
    agent_name: Optional[str] = typer.Option(None, "--agent-name", help="Override the agent name"),
    language: Optional[str] = typer.Option(None, "--language", help="Programming language (python, java)"),
    entrypoint: Optional[str] = typer.Option(None, "--entrypoint", help="Override the entrypoint command"),
    port: Optional[int] = typer.Option(None, "--port", help="Port to expose in the Dockerfile"),
    build_mode: Optional[str] = typer.Option(None, "--build-mode", help="Build strategy: local or cloud"),
    description: Optional[str] = typer.Option(None, "--description", help="Agent description"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for packaged workspace"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable detailed logging"),
) -> None:
```

## Typer — `build`

```python
def build(
    workspace: str = typer.Option(".", "-f", "--workspace", help="Path to the agent workspace directory", show_default=True),
    proxy: Optional[str] = typer.Option(None, "-p", "--proxy", help="Custom proxy URL for dependency resolution"),
    cloud_provider: Optional[str] = typer.Option(None, "--cloud-provider", help="Cloud provider name (e.g., huawei)"),
    output: Optional[str] = typer.Option(None, "--output", help="Output path for build artifacts"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable detailed logging"),
) -> None:
```

## Typer — `publish`

```python
def publish(
    workspace: str = typer.Option(".", "-f", "--workspace", help="Path to the agent workspace directory", show_default=True),
    version: Optional[str] = typer.Option(None, "--version", help="Semantic version string (e.g., v1.0.0)"),
    image_url: Optional[str] = typer.Option(None, "--image-url", help="Image repository URL (required in local build mode)"),
    image_username: Optional[str] = typer.Option(None, "--image-username", help="Username for image repository"),
    image_password: Optional[str] = typer.Option(None, "--image-password", help="Password for image repository"),
    description: Optional[str] = typer.Option(None, "--description", help="Agent description"),
    region: Optional[str] = typer.Option(None, "--region", help="Deployment region"),
    cloud_provider: Optional[str] = typer.Option(None, "--cloud-provider", help="Cloud provider name (e.g., huawei)"),
    provider: str = typer.Option("agentcube", "--provider", help="Target provider: 'agentcube' (AgentRuntime CR) or 'k8s' (Deployment/Service)"),
    node_port: Optional[int] = typer.Option(None, "--node-port", help="Specific NodePort to use (30000-32767) for K8s deployment"),
    replicas: Optional[int] = typer.Option(None, "--replicas", help="Number of replicas for K8s deployment (default: 1)"),
    namespace: Optional[str] = typer.Option(None, "--namespace", help="The namespace for the deployment"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable detailed logging"),
) -> None:
```

## Typer — `invoke`

```python
def invoke(
    workspace: str = typer.Option(".", "-f", "--workspace", help="Path to the agent workspace directory", show_default=True),
    payload: str = typer.Option("{}", "--payload", help="JSON-formatted input passed to the agent"),
    header_list: Optional[List[str]] = typer.Option(None, "--header", help="Custom HTTP headers (e.g., 'Authorization: Bearer token'). Can be specified multiple times."),
    provider: str = typer.Option("agentcube", "--provider", help="Target provider: 'agentcube' (AgentRuntime CR) or 'k8s' (Deployment/Service)"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable detailed logging"),
) -> None:
```

## Typer — `status`

```python
def status(
    workspace: str = typer.Option(".", "-f", "--workspace", help="Path to the agent workspace directory", show_default=True),
    provider: str = typer.Option("agentcube", "--provider", help="Target provider: 'agentcube' (AgentRuntime CR) or 'k8s' (Deployment/Service)"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable detailed logging"),
) -> None:
```

## Helper functions (`agentcube/cli/main.py`)

```python
def version_callback(value: bool) -> None: ...
def _handle_error(e: Exception, command_name: str, verbose: bool) -> None: ...  # prints, typer.Exit(1)
```

## Runtime classes

### `PackRuntime` (`agentcube/runtime/pack_runtime.py`)

```python
class PackRuntime:
    def __init__(self, verbose: bool = False) -> None: ...
    def pack(self, workspace_path: Path, **options: Any) -> Dict[str, Any]: ...
    def _validate_workspace_structure(self, workspace_path: Path) -> None: ...
    def _load_or_create_metadata(self, workspace_path: Path, options: Dict[str, Any]) -> AgentMetadata: ...
    def _apply_option_overrides(self, metadata: AgentMetadata, options: Dict[str, Any]) -> AgentMetadata: ...
    def _validate_language_compatibility(self, workspace_path: Path, metadata: AgentMetadata) -> None: ...
    def _validate_python_compatibility(self, workspace_path: Path) -> None: ...
    def _validate_java_compatibility(self, workspace_path: Path) -> None: ...
    def _process_dependencies(self, workspace_path: Path, metadata: AgentMetadata) -> None: ...
    def _process_python_dependencies(self, workspace_path: Path) -> None: ...
    def _process_java_dependencies(self, workspace_path: Path) -> None: ...
    def _generate_dockerfile(self, workspace_path: Path, metadata: AgentMetadata) -> Optional[Path]: ...
    def _generate_python_dockerfile(self, metadata: AgentMetadata) -> str: ...
    def _generate_java_dockerfile(self, metadata: AgentMetadata) -> str: ...
    def _update_pack_metadata(self, workspace_path: Path, metadata: AgentMetadata, dockerfile_path: Optional[Path]) -> None: ...
    def _prepare_output_path(self, workspace_path: Path, output_path: Optional[str]) -> Path: ...
    def _infer_entrypoint(self, workspace_path: Path, language: str) -> str: ...
```

### `BuildRuntime` (`agentcube/runtime/build_runtime.py`)

```python
class BuildRuntime:
    def __init__(self, verbose: bool = False) -> None: ...
    def build(self, workspace_path: Path, **options: Any) -> Dict[str, Any]: ...
    def _increment_version(self, workspace_path: Path, metadata) -> Any: ...
    def _validate_build_prerequisites(self, workspace_path: Path) -> None: ...
    def _build_local(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> Dict[str, Any]: ...
    def _build_cloud(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> Dict[str, Any]: ...
    def _update_build_metadata(self, workspace_path: Path, metadata, build_result: Dict[str, str], tag: str = "latest") -> None: ...
```

### `PublishRuntime` (`agentcube/runtime/publish_runtime.py`)

```python
class PublishRuntime:
    def __init__(self, verbose: bool = False, provider: str = "agentcube") -> None: ...
    def publish(self, workspace_path: Path, **options: Any) -> Dict[str, Any]: ...
    def _publish_cr_to_k8s(self, workspace_path: Path, metadata, **options: Any) -> Dict[str, Any]: ...
    def _publish_k8s(self, workspace_path: Path, metadata, **options: Any) -> Dict[str, Any]: ...
    def _prepare_image_for_publishing(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> str: ...
    def _prepare_local_image(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> str: ...
    def _prepare_cloud_image(self, workspace_path: Path, metadata, options: Dict[str, Any]) -> str: ...
    def _update_publish_metadata(self, workspace_path: Path, agent_info: Dict[str, Any]) -> None: ...
```

### `InvokeRuntime` (`agentcube/runtime/invoke_runtime.py`)

```python
class InvokeRuntime:
    def __init__(self, verbose: bool = False, provider: str = "agentcube") -> None: ...
    def invoke(self, workspace_path: Path, payload: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Any: ...
    def _validate_invoke_prerequisites(self, workspace_path: Path) -> Tuple[Any, str, str]: ...
    async def _invoke_agent_via_agentcube(self, agent_id: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]], endpoint: str, workspace_path: Path) -> Any: ...
    async def _direct_http_invocation(self, endpoint: str, payload: Dict[str, Any], headers: Optional[Dict[str, str]], workspace_path: Path) -> Dict[str, Any]: ...
```

**Implementation note:** `_invoke_agent_via_agentcube` only assigns `response` inside `if endpoint.startswith("http"):`; if the condition is false, `return response` may raise `UnboundLocalError` (as of extracted source).

### `StatusRuntime` (`agentcube/runtime/status_runtime.py`)

```python
class StatusRuntime:
    def __init__(self, verbose: bool = False, provider: str = "agentcube") -> None: ...
    def get_status(self, workspace_path: Path, provider: Optional[str] = None) -> Dict[str, Any]: ...
    def _get_k8s_status(self, metadata) -> Dict[str, Any]: ...
    def _get_cr_k8s_status(self, metadata) -> Dict[str, Any]: ...
```

## `DockerService` (`agentcube/services/docker_service.py`)

```python
class DockerService:
    def __init__(self, verbose: bool = False) -> None: ...
    def check_docker_available(self) -> bool: ...
    def build_image(
        self,
        dockerfile_path: Path,
        context_path: Path,
        image_name: str,
        tag: str = "latest",
        build_args: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]: ...
    def get_image_info(self, image_name: str) -> Dict[str, str]: ...
    def _get_image_info(self, image_name: str) -> Dict[str, str]: ...
    def _format_size(self, size_bytes: int) -> str: ...
    def push_image(
        self,
        image_name: str,
        registry_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> Dict[str, str]: ...
    def _docker_login_sdk(self, registry: Optional[str], username: str, password: str) -> None: ...
    def _tag_image_sdk(self, source_image: str, target_image: str) -> None: ...
    def remove_image(self, image_name: str) -> bool: ...
```

## `MetadataService` (`agentcube/services/metadata_service.py`)

```python
class MetadataService:
    def __init__(self, verbose: bool = False) -> None: ...
    def load_metadata(self, workspace_path: Path) -> AgentMetadata: ...
    def save_metadata(self, workspace_path: Path, metadata: AgentMetadata) -> None: ...
    def update_metadata(self, workspace_path: Path, updates: Dict[str, Any]) -> AgentMetadata: ...
    def validate_workspace(self, workspace_path: Path) -> bool: ...
    def _validate_python_workspace(self, workspace_path: Path, metadata: AgentMetadata) -> None: ...
    def _validate_java_workspace(self, workspace_path: Path, metadata: AgentMetadata) -> None: ...
```

## `KubernetesProvider` (`agentcube/services/k8s_provider.py`)

```python
class KubernetesProvider:
    def __init__(
        self,
        namespace: str = "default",
        verbose: bool = False,
        kubeconfig: Optional[str] = None,
    ) -> None: ...
    def _ensure_namespace(self) -> None: ...
    def deploy_agent(
        self,
        agent_name: str,
        image_url: str,
        port: int,
        entrypoint: Optional[str] = None,
        replicas: int = 1,
        node_port: Optional[int] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]: ...
    def _create_deployment(
        self,
        name: str,
        image_url: str,
        port: int,
        entrypoint: Optional[str],
        replicas: int,
        env_vars: Optional[Dict[str, str]],
    ) -> Dict[str, Any]: ...
    def _create_service(self, name: str, port: int, node_port: Optional[int]) -> Dict[str, Any]: ...
    def wait_for_deployment_ready(self, name: str, timeout: int = 120) -> None: ...
    def get_agent_status(self, agent_name: str) -> Dict[str, Any]: ...
    def delete_agent(self, agent_name: str) -> Dict[str, Any]: ...
    def _sanitize_name(self, name: str) -> str: ...
```

## `AgentCubeProvider` (`agentcube/services/agentcube_provider.py`)

```python
class AgentCubeProvider:
    def __init__(
        self,
        namespace: str = "default",
        verbose: bool = False,
        kubeconfig: Optional[str] = None,
    ) -> None: ...
    def _ensure_namespace(self) -> None: ...
    def deploy_agent_runtime(
        self,
        agent_name: str,
        image_url: str,
        port: int,
        entrypoint: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
        workload_manager_url: Optional[str] = None,
        router_url: Optional[str] = None,
        readiness_probe_path: Optional[str] = None,
        readiness_probe_port: Optional[int] = None,
    ) -> Dict[str, Any]: ...
    def _sanitize_name(self, name: str) -> str: ...
    def get_agent_runtime(self, name: str, namespace: str) -> Optional[Dict[str, Any]]: ...
```

CR API: `group="runtime.agentcube.volcano.sh"`, `version="v1alpha1"`, `plural="agentruntimes"`.

## `AgentMetadata` (Pydantic `BaseModel`)

| Field | Type | Default | `Field(..., description=...)` |
|-------|------|---------|--------------------------------|
| `agent_name` | `str` | (required) | Unique name identifying the agent |
| `description` | `Optional[str]` | `None` | Human-readable summary |
| `language` | `str` | `"python"` | Programming language used |
| `entrypoint` | `str` | (required) | Command to launch the agent |
| `port` | `int` | `8080` | Port exposed by the agent runtime |
| `build_mode` | `str` | `"local"` | Build strategy: local or cloud |
| `region` | `Optional[str]` | `None` | Deployment region |
| `version` | `Optional[str]` | `None` | Semantic version string for publishing |
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
| `session_id` | `Optional[str]` | `None` | The session ID for the agent |
| `k8s_deployment` | `Optional[Dict[str, Any]]` | `None` | Kubernetes deployment information |

Validators: `validate_language` → `['python','java']` lowercase; `validate_build_mode` → `['local','cloud']` lowercase; `validate_port` → `1..65535`.

## `MetadataOptions` (`agentcube/models/pack_models.py`)

Dataclass fields (all `Optional` unless noted):

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

```python
@classmethod
def from_options(cls, options: Dict[str, Any]) -> "MetadataOptions": ...
```

## Dependencies (`cmd/cli/pyproject.toml`)

**`[project]` dependencies:**

- `typer[all]>=0.9.0`
- `pydantic>=2.0.0`
- `pyyaml>=6.0`
- `httpx>=0.24.0`
- `docker>=6.0.0`
- `rich>=13.0.0`
- `packaging>=23.0`
- `importlib-resources>=6.0.0`
- `semver>=3.0.0`

**Optional `[project.optional-dependencies]`:**

- `k8s`: `kubernetes>=28.0.0`
- `dev`: `pytest>=7.4.0`, `pytest-asyncio>=0.21.0`, `pytest-cov>=4.1.0`, `ruff>=0.1.0`, `mypy>=1.5.0`, `pre-commit>=3.3.0`, `kubernetes>=28.0.0`
- `test`: `pytest>=7.4.0`, `pytest-asyncio>=0.21.0`, `pytest-cov>=4.1.0`, `pytest-mock>=3.11.0`, `httpx-mock>=0.10.0`

**Python:** `requires-python = ">=3.10"`.

## Top-level exports (`agentcube/__init__.py`)

- `__version__ = "0.1.0"`
- `__author__ = "AgentCube Community"`
- `__email__ = "agentcube@volcano.sh"`
- Imports: `app`, `PackRuntime`, `BuildRuntime`, `PublishRuntime`, `InvokeRuntime`
- `__all__` = `["app", "PackRuntime", "BuildRuntime", "PublishRuntime", "InvokeRuntime"]`  
  (`StatusRuntime` is not exported here.)
