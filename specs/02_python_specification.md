# AgentCube Python Source Specification

> Reverse-engineered from https://github.com/ShijunDeng/agentcube.git
> Generated at: 2026-03-21T03:09:00Z (Stage 1 of SDD Benchmark)

---

## 1. Repository Layout (Python)

| Area | Package Name | Path |
|------|-------------|------|
| CLI | agentcube-cli | cmd/cli/ |
| SDK | agentcube-sdk | sdk-python/ |
| Dify Plugin | (plugin) | integrations/dify-plugin/ |
| Example | pcap-analyzer | example/pcap-analyzer/ |

## 2. CLI Command Tree (Typer)

**App:** `agentcube`, console script: `kubectl-agentcube`

### Commands

| Command | Key Options |
|---------|------------|
| `pack` | --workspace/-f, --agent-name, --language, --entrypoint, --port, --build-mode, --description, --output |
| `build` | --workspace/-f, --proxy/-p, --cloud-provider, --output |
| `publish` | --workspace/-f, --version, --image-url, --image-username, --image-password, --provider (agentcube\|k8s), --node-port, --replicas, --namespace |
| `invoke` | --workspace/-f, --payload, --header, --provider |
| `status` | --workspace/-f, --provider |

Global: `--version` (eager), `--verbose`/`-v`

## 3. CLI Runtime Classes

| Class | Method | Description |
|-------|--------|-------------|
| PackRuntime | pack(workspace_path, **options) | Generate Dockerfile + metadata |
| BuildRuntime | build(workspace_path, **options) | Docker build, auto version bump |
| PublishRuntime | publish(workspace_path, **options) | Deploy via AgentCube CR or K8s |
| InvokeRuntime | invoke(workspace_path, payload, headers) | HTTP POST via httpx |
| StatusRuntime | get_status(workspace_path, provider) | Query deployment status |

## 4. CLI Services

| Service | Key Methods |
|---------|------------|
| DockerService | check_docker_available, build_image, push_image, remove_image |
| MetadataService | load_metadata, save_metadata, update_metadata, validate_workspace |
| KubernetesProvider | deploy_agent, wait_for_deployment_ready, get_agent_status, delete_agent |
| AgentCubeProvider | deploy_agent_runtime, get_agent_runtime |

## 5. Data Models

**AgentMetadata** (Pydantic BaseModel): agent_name, description, language, entrypoint, port, build_mode, region, version, image, registry_url, registry_username, registry_password, agent_endpoint, workload_manager_url, router_url, readiness_probe_path, readiness_probe_port, agent_id, session_id, auth, requirements_file, k8s_deployment

**MetadataOptions** (dataclass): agent_name, language, entrypoint, port, build_mode, requirements_file, description, workload_manager_url, router_url, readiness_probe_path, readiness_probe_port, registry_url, registry_username, registry_password, agent_endpoint

## 6. SDK Public API

### CodeInterpreterClient
- Context manager (enter/exit → stop)
- `execute_command(command, timeout)` → str
- `run_code(language, code, timeout)` → str
- `write_file(content, remote_path)`
- `upload_file(local_path, remote_path)`
- `download_file(remote_path, local_path)`
- `list_files(path)`
- `stop()`

### AgentRuntimeClient
- Context manager (enter/exit → close)
- `invoke(payload, timeout)` → Any
- `close()`

### HTTP Clients
- ControlPlaneClient: create_session (POST /v1/code-interpreter), delete_session
- CodeInterpreterDataPlaneClient: execute_command, run_code, write_file, upload_file, download_file, list_files
- AgentRuntimeDataPlaneClient: bootstrap_session_id, invoke (SESSION_HEADER = "x-agentcube-session-id")

### Exceptions
- AgentCubeError, CommandExecutionError(exit_code, stderr, command), SessionError, DataPlaneError

## 7. Dependencies

**CLI:** typer[all]>=0.9.0, pydantic>=2.0.0, pyyaml>=6.0, httpx>=0.24.0, docker>=6.0.0, rich>=13.0.0, packaging>=23.0, semver>=3.0.0
**SDK:** requests, PyJWT>=2.0.0, cryptography
