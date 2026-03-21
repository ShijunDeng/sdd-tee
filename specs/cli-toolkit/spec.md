# AgentCube CLI (cli-toolkit) Specification

## Purpose

Command-line tool (`kubectl-agentcube`) for packaging, building, publishing, invoking, and checking status of AI agents against AgentCube or standard Kubernetes.

## Requirements

### Requirement: Global CLI options
The system SHALL expose a Typer application named `agentcube` with global options on the root callback.

#### Scenario: Version display
- **GIVEN** the CLI is installed and importable
- **WHEN** the user passes `--version` (eager option, `Optional[bool]`, default `None`)
- **THEN** the CLI SHALL print `AgentCube CLI (kubectl agentcube) version: {__version__}` (Rich markup) and exit without running a subcommand (`typer.Exit()`), where `__version__` is `0.1.0` from `agentcube.__init__`

#### Scenario: Global verbose logging
- **GIVEN** the user passes `--verbose` / `-v` (`bool`, default `False`) on the root callback
- **WHEN** the callback runs
- **THEN** the system SHALL call `logging.basicConfig(level=logging.DEBUG)`

### Requirement: `pack` command
The system SHALL provide `pack` to validate and prepare a workspace, merge CLI overrides into metadata, optionally generate a `Dockerfile`, and report paths.

#### Scenario: Options and defaults
- **GIVEN** the user runs `pack`
- **WHEN** options are omitted
- **THEN** the CLI SHALL use: `workspace` = `"."` (`-f` / `--workspace`, `str`); `agent_name` = `None` (`--agent-name`, `Optional[str]`); `language` = `None` (`--language`); `entrypoint` = `None` (`--entrypoint`); `port` = `None` (`--port`, `Optional[int]`); `build_mode` = `None` (`--build-mode`); `description` = `None` (`--description`); `output` = `None` (`--output`); `verbose` = `False` (`--verbose`, command-local)

#### Scenario: Successful pack
- **GIVEN** a valid workspace path
- **WHEN** `pack` completes without exception
- **THEN** the CLI SHALL print success with `agent_name`, resolved `workspace_path`, and `metadata_path` (reported as `{final_workspace}/agent_metadata.yaml`), using a Rich `Progress` spinner during work

#### Scenario: Pack failure handling
- **GIVEN** `PackRuntime.pack` raises
- **WHEN** `verbose` is `True`
- **THEN** the CLI SHALL print `Error packaging agent: {e}` in red, print a full traceback, and exit with code `1`

### Requirement: `build` command
The system SHALL build a container image from a packaged workspace using local Docker when `build_mode` is `local` (default in metadata), with optional proxy and tag derived from metadata version.

#### Scenario: Options and defaults
- **GIVEN** the user runs `build`
- **WHEN** options are omitted
- **THEN** defaults SHALL be: `workspace` = `"."` (`-f` / `--workspace`); `proxy` = `None` (`-p` / `--proxy`); `cloud_provider` = `None` (`--cloud-provider`); `output` = `None` (`--output`); `verbose` = `False` (`--verbose`)

#### Scenario: Local Docker build prerequisites
- **GIVEN** `build_mode` resolves to `local`
- **WHEN** Docker is unavailable
- **THEN** `BuildRuntime` SHALL raise `RuntimeError("Docker is not available or not running")` surfaced via CLI error handling

#### Scenario: Version increment on build
- **GIVEN** a successful local build path
- **WHEN** `BuildRuntime.build` runs
- **THEN** the system SHALL increment `metadata.version` (patch bump for `X.Y.Z`, or append `.1` / fallback `{version}-1`) before build and revert the version in metadata if build fails

### Requirement: `publish` command
The system SHALL publish/deploy using provider `agentcube` (AgentRuntime CR) or `k8s` (Deployment + NodePort Service), preparing the image via Docker push or explicit image URL as implemented in `PublishRuntime`.

#### Scenario: Options and defaults
- **GIVEN** the user runs `publish`
- **THEN** defaults SHALL include: `workspace` = `"."`; `version` = `None` (`--version`); `image_url` = `None` (`--image-url`); `image_username` = `None` (`--image-username`); `image_password` = `None` (`--image-password`); `description` = `None`; `region` = `None` (`--region`); `cloud_provider` = `None`; `provider` = `"agentcube"` (`--provider`); `node_port` = `None` (`--node-port`, `Optional[int]`); `replicas` = `None` (`--replicas`); `namespace` = `None` (`--namespace`); `verbose` = `False`

#### Scenario: AgentCube provider prerequisites
- **GIVEN** `provider` is `agentcube`
- **WHEN** metadata lacks `router_url` or `workload_manager_url`
- **THEN** the system SHALL raise `ValueError` with message requiring both fields in `agent_metadata.yaml`

#### Scenario: Standard Kubernetes publish flow
- **GIVEN** `provider` is `k8s` and Kubernetes client initializes
- **WHEN** publish proceeds
- **THEN** the system SHALL call `KubernetesProvider.deploy_agent`, then `wait_for_deployment_ready(..., timeout=120)`, updating metadata with deployment info; on readiness failure it SHALL raise `RuntimeError` after recording error in metadata

### Requirement: `invoke` command
The system SHALL POST JSON to the published agent endpoint, parse `--payload` as JSON, merge optional `--header` entries, and for AgentRuntime CR deployments rewrite the URL to `{base}/v1/namespaces/{namespace}/agent-runtimes/{agent_name}/invocations/` when `k8s_deployment.type == "AgentRuntime"`.

#### Scenario: Options and defaults
- **GIVEN** the user runs `invoke`
- **THEN** defaults SHALL be: `workspace` = `"."`; `payload` = `"{}"` (`--payload`, `str`); `header_list` = `None` (`--header`, repeatable `List[str]`); `provider` = `"agentcube"`; `verbose` = `False`

#### Scenario: Invalid payload
- **GIVEN** `payload` is not valid JSON
- **WHEN** the command parses it
- **THEN** the CLI SHALL print invalid JSON in red and exit with code `1` (before `_handle_error`)

#### Scenario: Invalid header format
- **GIVEN** a header string without a single `:` separator
- **WHEN** headers are parsed
- **THEN** the CLI SHALL print expected `key:value` format and exit with code `1`

#### Scenario: Session header on invoke
- **GIVEN** metadata contains `session_id`
- **WHEN** `InvokeRuntime.invoke` runs
- **THEN** the HTTP client SHALL add header `X-Agentcube-Session-Id` (same spelling as response handling) to the request

### Requirement: `status` command
The system SHALL load workspace metadata and display agent status in a Rich `Table`, exiting with code `1` when status is `not_published` or `error`.

#### Scenario: Options and defaults
- **GIVEN** the user runs `status`
- **THEN** defaults SHALL be: `workspace` = `"."`; `provider` = `"agentcube"`; `verbose` = `False`

#### Scenario: Not published
- **GIVEN** metadata has no `agent_id`
- **WHEN** `get_status` returns `status == "not_published"`
- **THEN** the CLI SHALL print guidance to publish first and exit with code `1`

### Requirement: Workspace validation (pack path)
The system SHALL validate that the workspace path exists and is a directory; for Python, require at least one `*.py` file; for Java, require `pom.xml`.

#### Scenario: Missing workspace
- **GIVEN** `workspace_path` does not exist
- **WHEN** `PackRuntime._validate_workspace_structure` runs
- **THEN** the system SHALL raise `ValueError` with a message that the directory does not exist

#### Scenario: Python workspace without Python files
- **GIVEN** `metadata.language == "python"`
- **WHEN** no `*.py` exists in the workspace root
- **THEN** the system SHALL raise `ValueError("No Python files found in workspace")`

### Requirement: Metadata file format
The system SHALL persist agent configuration as YAML. The primary filename SHALL be `agent_metadata.yaml`; loading SHALL fall back to `agent.yaml` then `metadata.yaml` if the primary file is missing.

#### Scenario: Save location
- **GIVEN** metadata is saved
- **WHEN** `MetadataService.save_metadata` runs
- **THEN** the file SHALL be written to `{workspace}/agent_metadata.yaml` using `yaml.dump` with `default_flow_style=False`, `indent=2`, `sort_keys=False`, excluding `None` fields via `model_dump(exclude_none=True)`

#### Scenario: Schema validation
- **GIVEN** YAML is loaded
- **WHEN** fields violate `AgentMetadata` validators
- **THEN** Pydantic SHALL reject unsupported `language` / `build_mode` or invalid `port` range

### Requirement: Docker integration
The system SHALL use the Docker SDK (`docker.from_env()`) to build images, push to a registry when configured, and optionally remove images.

#### Scenario: Build image
- **GIVEN** Docker is running
- **WHEN** `DockerService.build_image` is called
- **THEN** it SHALL tag `{image_name}:{tag}`, pass optional `buildargs` from proxy settings, and return `image_name`, `image_id`, `image_size`, `build_time`

#### Scenario: Push image
- **GIVEN** a local image name and optional `registry_url` / credentials
- **WHEN** `DockerService.push_image` runs
- **THEN** it SHALL login if username and password are provided, retag when needed, stream push logs, and return `pushed_image` and `push_time`

#### Scenario: Remove image
- **GIVEN** `DockerService.remove_image(image_name)` is called
- **WHEN** removal succeeds
- **THEN** it SHALL return `True`; on failure it SHALL log a warning and return `False`

### Requirement: Kubernetes — standard provider
The system SHALL create or patch `Deployment` and `NodePort` `Service`, wait for rollout, report pod status, and support deletion.

#### Scenario: Deploy agent
- **GIVEN** `KubernetesProvider.deploy_agent` is called
- **WHEN** resources are applied
- **THEN** the result SHALL include `deployment_name`, `service_name`, `namespace`, `replicas`, `container_port`, `node_port`, `service_url` as `http://localhost:{node_port}`

#### Scenario: Wait for ready
- **GIVEN** a deployment name
- **WHEN** `wait_for_deployment_ready` exceeds `timeout` seconds (default `120`)
- **THEN** it SHALL raise `TimeoutError`

#### Scenario: Delete agent
- **GIVEN** `delete_agent` is called
- **WHEN** deletion completes
- **THEN** it SHALL return `{"status": "deleted", "deployment_name", "namespace"}` ignoring 404 on individual deletes

### Requirement: Kubernetes — AgentCube AgentRuntime CR
The system SHALL create or patch an `AgentRuntime` custom object in group `runtime.agentcube.volcano.sh`, version `v1alpha1`, plural `agentruntimes`.

#### Scenario: Deploy CR
- **GIVEN** required readiness probe fields exist in metadata
- **WHEN** `AgentCubeProvider.deploy_agent_runtime` runs
- **THEN** it SHALL embed `WORKLOAD_MANAGER_URL` / `ROUTER_URL` from parameters or environment when missing in `env_vars`, set `sessionTimeout` to `"15m"` and `maxSessionDuration` to `"8h"`, and reference `imagePullSecrets` `[{"name": "default-secret"}]`

### Requirement: AgentCube provider integration (CLI)
The system SHALL use `AgentCubeProvider` for `provider=agentcube` publish/status flows and `KubernetesProvider` for `provider=k8s`.

#### Scenario: Status for AgentRuntime
- **GIVEN** `provider` is `agentcube` and the CR exists
- **WHEN** `StatusRuntime._get_cr_k8s_status` runs
- **THEN** status SHALL be read from `cr_object["status"]` when present (`status`, `agentEndpoint`), else `created_no_status`, else `not_found_in_k8s`

### Requirement: Error handling patterns
The system SHALL use `_handle_error(e, command_name, verbose)` for subcommand exceptions: print `Error {command_name}: {e}` in red; if `verbose`, print traceback; raise `typer.Exit(1)`.

#### Scenario: Subcommand verbose vs global verbose
- **GIVEN** a subcommand’s local `--verbose` is `True` but global `-v` was not passed
- **WHEN** an error occurs in that subcommand
- **THEN** traceback SHALL still be printed because `_handle_error` receives the subcommand’s `verbose` flag

---

**Note:** The implementation uses `agent_metadata.yaml` as the canonical metadata filename (with `agent.yaml` / `metadata.yaml` fallbacks for load). Documentation that refers to `agentcube.yaml` SHALL be treated as naming drift unless a separate file is introduced in code.
