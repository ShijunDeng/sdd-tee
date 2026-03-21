---
sidebar_position: 3
---

# Building custom agent runtimes

Agent runtimes are ordinary **container images** that expose HTTP(S) on ports declared in your CRD. AgentCube handles **scheduling**, **routing**, and **session policy**; your image handles **agent logic**.

## AgentRuntime checklist

1. **Container listens** on a stable port (for example `8080`).
2. **`AgentRuntime.spec.targetPorts`** lists each `pathPrefix`, `name`, `port`, and `protocol` (`HTTP` or `HTTPS`) the Router should map.
3. **`AgentRuntime.spec.podTemplate.spec`** embeds a full `PodSpec`:
   - Main agent container + optional PicoD sidecar (for hybrid tool use)
   - Resource requests/limits for scheduling
   - `runtimeClassName` at pod or template level for isolation
   - Service account if your agent calls the Kubernetes API

4. **Session policy** — Set `sessionTimeout` and `maxSessionDuration` to match your product’s UX.

## CodeInterpreter checklist

1. Image includes **PicoD** (or your fork) when using `authMode: picod`.
2. Inject **`PICOD_AUTH_PUBLIC_KEY`** from a Secret synced to the Router identity public key.
3. Set **`CodeInterpreter.spec.template.image`** and resource limits appropriate for interpreter workloads (CPU-bound vs memory-bound).
4. Tune **`warmPoolSize`** for latency vs cost.

## CLI-assisted workflow

The `kubectl-agentcube` CLI can scaffold metadata, build images, and publish to Kubernetes or an `AgentRuntime`:

```bash
kubectl-agentcube pack --workspace ./my-agent --port 8080
kubectl-agentcube build --workspace ./my-agent --image-prefix ghcr.io/org
kubectl-agentcube publish --provider k8s --workspace ./my-agent
```

See `docs/design/AgentRun-CLI-Design.md` for command details.

## Testing images locally

Build with `docker build`, run with `docker run`, and only then promote to a cluster CRD. For PicoD, verify JWTs end-to-end by port-forwarding the Router and creating a session through the Python SDK.
