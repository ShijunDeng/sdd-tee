---
sidebar_position: 2
---

# Hello world agent

Build and publish a minimal agent using the AgentCube CLI and Helm-installed control plane.

## Prerequisites

- AgentCube [installed](../getting-started.md) in namespace `agentcube`
- Docker for local image builds
- `kubectl-agentcube` installed (`pip install -e ./cmd/cli` from the repo)

## Use the sample workspace

The repository includes `cmd/cli/examples/hello-agent` with a tiny HTTP server.

```bash
cd cmd/cli/examples/hello-agent
```

## Pack metadata

```bash
kubectl-agentcube pack \
  --workspace . \
  --name hello-agent \
  --port 8080 \
  --namespace default
```

This creates `agent_metadata.yaml` and ensures a `Dockerfile` exists.

## Build the image

```bash
kubectl-agentcube build --workspace . --image-prefix ghcr.io/<org>/hello-agent
```

## Publish to Kubernetes

```bash
kubectl-agentcube publish --provider k8s --workspace . --wait
```

Alternatively, publish an `AgentRuntime` when your cluster integration expects `--provider agentcube`.

## Invoke

```bash
kubectl-agentcube invoke --workspace . --payload '{"input":"world"}'
```

You should see the agent’s JSON response in the terminal.

## Next steps

- Add dependencies in `requirements.txt` and rebuild
- Define an `AgentRuntime` CR that references your image and `targetPorts`
- Read [Architecture → Components](../architecture/components.md) to understand how the Router reaches your Pod
