---
sidebar_position: 2
---

# Components

## Workload Manager

**Binary:** `cmd/workload-manager` (built as `workloadmanager` in `bin/`)

The Workload Manager hosts Kubernetes controllers that:

- Reconcile **`AgentRuntime`** and **`CodeInterpreter`** specifications into runnable sandboxes
- Maintain **warm pools** for interpreters when `warmPoolSize` is set
- Run **garbage collection** for idle or expired sessions (aligned with CRD timeouts)
- Integrate with **Volcano** scheduling hooks when enabled via chart values

It exposes HTTP endpoints for health and operational introspection (`pkg/workloadmanager/server.go`).

## Router

**Binary:** `cmd/router`

The Router is the **session-aware ingress** for AgentCube invocation URLs. It:

- Proxies to the correct backend for each active session
- Issues **RS256 JWTs** for PicoD using keys stored in Secret `picod-router-identity`
- Limits **in-flight requests** with a weighted semaphore (returns HTTP 429 when saturated)
- Uses **Redis** for session state via `pkg/store`

Health endpoints support Kubernetes probes (`/health/live`, `/health/ready`).

## PicoD

**Binary:** `cmd/picod`

PicoD runs **inside** the sandbox image and exposes:

- `POST /api/execute` — run commands with timeout and working directory
- File upload, list, and download under `/api/files`

All `/api/*` routes require a valid **Bearer JWT** unless you explicitly disable auth at the CRD level (not recommended in production). PicoD loads the Router’s **public key** from `PICOD_AUTH_PUBLIC_KEY`.

## AgentD

**Binary:** `cmd/agentd`

AgentD provides a controller entrypoint aligned with the broader **agents** ecosystem. Deployments may run AgentD alongside or instead of certain legacy reconciler paths depending on feature gates and chart configuration. Consult `manifests/charts/base` for the active Deployment templates in your version.

## Redis

Redis (or Valkey) is **not** optional for the default Router + Workload Manager stack: both components read and write session metadata through `pkg/store`. Configure `redis.addr` (and optional password) in Helm `values.yaml`.

## See also

- `docs/design/router-proposal.md`
- `docs/design/picod-proposal.md`
- `README.md` at repository root for directory layout
