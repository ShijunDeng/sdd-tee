# Runtime Template Proposal

AgentCube separates **what a sandbox is** (image, resources, pod shape) from **how many run** and **how traffic reaches them**. This document describes the template model for **AgentRuntime** and **CodeInterpreter** warm pools.

## AgentRuntime: `SandboxTemplate`

`AgentRuntime.spec.podTemplate` embeds a full Kubernetes **`PodSpec`** inside `SandboxTemplate`:

| Field | Use |
|-------|-----|
| `labels` / `annotations` | Merged into sandbox pod metadata for scheduling, observability, network policy selectors. |
| `spec` | **Required** — containers, volumes, `runtimeClassName` at pod level, service account, security context, etc. |

**Target ports** (`spec.targetPorts`) are orthogonal to the pod template: they declare **HTTP(S) routing** — `pathPrefix`, stable `name`, `port`, and `protocol` (`HTTP` / `HTTPS`). The Workload Manager and Router use this metadata to build Services and ingress-style paths.

### Session policy

- `sessionTimeout` — idle reclaim (default **15m**).
- `maxSessionDuration` — hard lifetime cap (default **8h**).

These values should be reflected in Router session TTL and controller garbage collection.

## CodeInterpreter: `CodeInterpreterSandboxTemplate`

Code interpreters use a **narrower** template focused on a single main container:

| Field | Use |
|-------|-----|
| `image` | **Required** interpreter image (includes PicoD sidecar arrangement via multi-container pod if desired). |
| `imagePullPolicy` / `imagePullSecrets` | Registry auth. |
| `environment` | Inject `PICOD_AUTH_PUBLIC_KEY`, workspace paths, feature flags. |
| `command` / `args` | Override entrypoint for custom shells or interpreters. |
| `resources` | CPU/memory requests and limits — critical for bin-packing on GPU/CPU nodes. |
| `runtimeClassName` | e.g. gVisor, Kata, Kuasar for stronger isolation. |
| `labels` / `annotations` | Same as AgentRuntime template merging. |

**Ports** (`spec.ports`) mirror `TargetPort` semantics for the interpreter HTTP surface.

## Warm pools: `warmPoolSize`

`CodeInterpreter.spec.warmPoolSize` instructs the controller to maintain **N idle ready sandboxes**:

- Reduces **cold start latency** for interactive sessions.
- Increases **steady-state cost** — operators balance pool size against cluster quota.

Warm pool semantics:

1. Controller pre-creates Pods (or ReplicaSet-like sets) up to `warmPoolSize`.
2. When a user session **claims** a sandbox, another warm instance is prepared if under cap.
3. On session end, pod is recycled or deleted per garbage collection policy.

**AgentRuntime** warm pooling (if not yet exposed as a field) can follow the same pattern: optional `warmPoolSize` in a future API revision or via a higher-level `SandboxWarmPool` CRD.

## SandboxWarmPool (conceptual)

A dedicated **`SandboxWarmPool`** CRD could generalize warm pooling across multiple runtimes:

- Selector for `AgentRuntime` name + namespace
- Min/max ready count
- Priority class and node affinity for pool placement

This is a **natural extension** once core reconciliation stabilizes.

## CodeInterpreter warm pools in practice

1. Define `CodeInterpreter` with `template.image` pointing to a PicoD-enabled interpreter image.
2. Set `warmPoolSize` based on expected concurrent sessions (e.g. 3–10 for dev, 50+ for shared services).
3. Set `authMode: picod` and distribute Router public key via env.
4. Monitor `status.ready` and pod metrics; scale pool down during off-peak.

## Testing templates

- Validate **`PodSpec`** with `kubectl apply --dry-run=server` in CI.
- Use **NetworkPolicy** dry-run to ensure only Router can reach PicoD port.

## References

- `pkg/apis/runtime/v1alpha1/types.go` — `SandboxTemplate`, `CodeInterpreterSandboxTemplate`, `TargetPort`
- `pkg/workloadmanager/sandbox_builder.go` — materialization logic
