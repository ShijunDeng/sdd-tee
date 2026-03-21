# AgentCube: Kubernetes-Native AI Agent Workload Management

## Motivation

AI agent platforms increasingly run **long-lived, stateful sandboxes** (code interpreters, tool-using agents, retrieval pipelines) on Kubernetes. Generic workload controllers treat these like batch jobs or stateless services, which leads to poor utilization, weak session semantics, and ad hoc security around in-sandbox execution.

**AgentCube** (a [Volcano](https://github.com/volcano-sh/volcano) subproject) provides a **first-class control plane** for agent workloads: declarative runtime templates, managed interpreter pools, session-aware routing, and integration with the broader Kubernetes agents ecosystem (`agents.x-k8s.io`).

## Goals

1. **Declarative runtimes** — Operators define reusable **AgentRuntime** templates (pod shape, exposed ports, session policy) and **CodeInterpreter** pools (warm capacity, auth mode).
2. **Predictable lifecycle** — Controllers reconcile desired state to Pods, Services, and session records; idle and max session durations are enforced consistently.
3. **Secure data plane** — Edge **Router** issues short-lived JWTs for upstream calls; **PicoD** inside sandboxes validates RS256 tokens before executing commands or touching the workspace.
4. **Operational clarity** — Health endpoints, Redis-backed coordination, and Helm-based deployment align with cluster best practices.

## Non-goals (initial phase)

- Replacing Volcano’s batch/queue semantics for non-agent workloads.
- Hosting model weights or serving LLM inference (AgentCube focuses on **agent sandbox** placement and routing).

## Architecture overview

```
Clients / SDKs
      │
      ▼
┌─────────────┐     ┌──────────────────┐     ┌─────────────┐
│   Router    │────▶│ Workload Manager │────▶│ Kubernetes  │
│ (edge HTTP) │     │  (reconcilers)   │     │   API       │
└─────────────┘     └──────────────────┘     └─────────────┘
      │                        │                     │
      │                        │                     ▼
      │                        │              Pods / Services
      │                        │              (sandboxes)
      ▼                        ▼
   Redis / Valkey         AgentCube CRDs
```

- **Router** — Session-aware reverse proxy; maps `/v1/namespaces/.../agent-runtimes|code-interpreters/.../invocations/*` to backend sandboxes; optional concurrency limits.
- **Workload Manager** — Reconciles **AgentRuntime**, **CodeInterpreter**, and related sandbox CRs; builds pod specs from templates; garbage collection and cache layers interact with the store.
- **PicoD** — In-sandbox daemon: `/api/execute`, file upload/list/download; JWT middleware using the Router’s public key.
- **AgentD** — Companion controller binary in the agents ecosystem alignment path (namespace may vary by deployment); participates in sandbox lifecycle where enabled.

See also: `docs/design/images/agentcube.svg`.

## Custom Resource Definitions (CRDs)

Group: `runtime.agentcube.volcano.sh/v1alpha1`

### AgentRuntime (`agentruntimes`, shortName `ar`)

Defines a **reusable template** for agent sandboxes.

| Area | Purpose |
|------|---------|
| `spec.targetPorts` | HTTP(S) path prefixes, stable port names, listener ports — used for ingress routing metadata. |
| `spec.podTemplate` | Full `PodSpec` (`SandboxTemplate`) for sandbox instances. |
| `spec.sessionTimeout` | Idle reclaim (default `15m`). |
| `spec.maxSessionDuration` | Hard cap on session lifetime (default `8h`). |
| `status.conditions` | Standard Kubernetes-style conditions. |

### CodeInterpreter (`codeinterpreters`, shortName `ci`)

Defines a **managed code interpreter pool** with optional warm capacity.

| Area | Purpose |
|------|---------|
| `spec.ports` | Same routing shape as `targetPorts` for interpreter HTTP(S) endpoints. |
| `spec.template` | `CodeInterpreterSandboxTemplate`: image, resources, env, optional `runtimeClassName`, pull secrets. |
| `spec.warmPoolSize` | Number of idle sandboxes to keep ready. |
| `spec.authMode` | `picod` (default) or `none` — selects how sessions authenticate to PicoD. |
| `spec.sessionTimeout` / `maxSessionDuration` | Same semantics as AgentRuntime. |
| `status.ready` | High-level readiness for the pool. |

### Related agents ecosystem types

The repository also includes **Sandbox** and **SandboxClaims** under `agentsandbox` APIs for binding identity and quota to sessions (`sessionID` on claims). These complement AgentCube runtimes when integrated with upstream agent controllers.

## Components summary

| Component | Role |
|-----------|------|
| **Router** | Edge HTTP API, session resolution, reverse proxy, JWT issuance for PicoD, global concurrency semaphore. |
| **Workload Manager** | CRD reconciliation, sandbox materialization, Redis store integration, admin/health HTTP server. |
| **PicoD** | Process execution and workspace file API inside the sandbox; RS256 JWT validation. |
| **AgentD** | Optional dedicated agent controller entrypoint for ecosystem alignment. |

## Deployment notes

- **Redis or Valkey** — Shared by Router and Workload Manager (`REDIS_ADDR`); configure via Helm `values.yaml`.
- **Identity Secret** — Router loads or creates `picod-router-identity` (RSA key pair) in `AGENTCUBE_NAMESPACE` for signing upstream tokens; PicoD receives the **public** key via `PICOD_AUTH_PUBLIC_KEY`.

## References

- API types: `pkg/apis/runtime/v1alpha1/types.go`
- Helm chart: `manifests/charts/base/`
- User guide: `docs/getting-started.md` and Docusaurus site under `docs/agentcube/`
