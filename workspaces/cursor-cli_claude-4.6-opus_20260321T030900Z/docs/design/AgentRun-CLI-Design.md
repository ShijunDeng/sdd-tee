# AgentRun CLI Design (`kubectl-agentcube`)

The AgentCube CLI packages the **agent developer workflow** from a workspace on disk to a running runtime on Kubernetes or an **AgentRuntime** custom resource.

## Command surface

| Command | Purpose |
|---------|---------|
| `pack` | Scaffold or refresh `Dockerfile` (if missing) and **`agent_metadata.yaml`** from flags and workspace layout. |
| `build` | Build the container image (default: local Docker), bump semver patch, optional `--tag-latest`. |
| `publish` | Push desired state to **`agentcube`** (AgentRuntime CR) or **`k8s`** (Deployment), with optional `--wait`. |
| `invoke` | `POST` JSON to the configured agent HTTP endpoint (from metadata). |
| `status` | Print deployment / CR status for the workspace agent. |

Global options: `--version`, `--verbose` / `-v`.

Implementation entrypoint: `cmd/cli/agentcube/cli/main.py` (Typer app name `kubectl-agentcube`).

## Typical workflow

1. **Initialize metadata** — `kubectl-agentcube pack --workspace ./my-agent --name my-agent --port 8080`
2. **Implement** — Add agent HTTP server and dependencies (`requirements.txt`, etc.).
3. **Build** — `kubectl-agentcube build --workspace ./my-agent --image-prefix ghcr.io/myorg`
4. **Publish** — `kubectl-agentcube publish --provider k8s --workspace ./my-agent`  
   or `--provider agentcube` when targeting an **AgentRuntime** CR.
5. **Verify** — `kubectl-agentcube status --workspace ./my-agent`
6. **Test traffic** — `kubectl-agentcube invoke --workspace ./my-agent --payload '{"input":"hello"}'`

## `pack` behavior

Key flags:

- `--name`, `--agent-version`, `--description`, `--author`
- `--base-image` (default `python:3.11-slim`)
- `--port` (container listen port)
- `--namespace` (default Kubernetes namespace recorded in metadata)

Produces a machine-readable result (JSON when verbose) including the resolved `workspace` path.

## `build` behavior

- Optional `--provider` as a **build backend hint** (extensibility hook; default local Docker).
- `--image-prefix` sets repository prefix for the built image tag.
- `--tag-latest` duplicates the `latest` tag.

Returns `image`, `version`, and optional `logs` (verbose).

## `publish` behavior

| Provider | Meaning |
|----------|---------|
| `agentcube` | Apply/update **AgentRuntime** (or AgentCube-specific publish path) from workspace metadata. |
| `k8s` | Create/update **Deployment** resources; `--wait` waits for readiness. |

`--kube-context` selects the kubeconfig context.

## `invoke` and `status`

- **invoke** — Body from `--payload` (JSON string) or `--payload-file`. Default body `{"input":""}`. Optional `--provider` is stored under `_meta.provider` in the payload for tracing only.
- **status** — `--provider` overrides `agentcube` vs `k8s` when not inferred from metadata.

## Metadata format (`agent_metadata.yaml`)

The pack/publish/invoke path expects a **workspace root metadata file** (consumed by `metadata_service` and runtime operations) capturing at minimum:

- **Agent identity** — `name`, `version`, human-readable `description`, `author`
- **Image** — Built image reference after `build`
- **Networking** — Listen `port`, optional path prefixes if customized
- **Kubernetes** — Target `namespace`, optional labels/annotations for publish
- **Routing hints** — Fields used by `InvokeRuntime` / `StatusRuntime` to locate Service or CR-backed endpoints

Exact schema is defined by `cmd/cli/agentcube/models/pack_models.py` and services under `cmd/cli/agentcube/services/`. Treat metadata as the **single source of truth** for CLI operations against a workspace.

## Extensibility

- **Providers** — Additional publish or build backends can register without changing the top-level command names.
- **Verbose mode** — Rich tracebacks and structured JSON for automation and CI.

## Security considerations

- Never commit registry credentials; use cluster pull secrets referenced in **AgentRuntime** / **CodeInterpreter** pod templates.
- `invoke` sends user-controlled JSON; ensure agents validate input server-side.
