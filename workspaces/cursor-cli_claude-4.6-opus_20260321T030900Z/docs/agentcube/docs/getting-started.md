---
sidebar_position: 2
---

# Getting started

This guide installs AgentCube on a Kubernetes cluster using the Helm chart in the repository.

## Prerequisites

- **Kubernetes ≥ 1.24** (1.28+ recommended for recent CRD and API behavior)
- **`kubectl`** configured for your cluster
- **[Helm 3](https://helm.sh/docs/intro/install/)** (3.14+ recommended)
- **Redis** or **Valkey** reachable from the namespace where AgentCube runs (Router and Workload Manager use `REDIS_ADDR`)

Optional: [kind](https://kind.sigs.k8s.io/) or another local cluster for development.

## Install agent-sandbox CRDs (AgentCube APIs)

Apply the AgentCube runtime CRDs from the repository root:

```bash
kubectl apply -f manifests/charts/base/crds/
```

You should see APIs such as:

- `agentruntimes.runtime.agentcube.volcano.sh` — `AgentRuntime`
- `codeinterpreters.runtime.agentcube.volcano.sh` — `CodeInterpreter`

## Deploy Redis or Valkey

AgentCube expects a Redis-compatible endpoint. Example: install a small Redis in the same namespace or reuse a managed service.

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install redis bitnami/redis --namespace agentcube --create-namespace
```

Note the master service DNS name (for example `redis-master.agentcube.svc.cluster.local:6379`) for the next step.

## Configure Helm values

Create `my-values.yaml`:

```yaml
redis:
  addr: redis-master.agentcube.svc.cluster.local:6379
  password: ""

router:
  rbac:
    create: true

workloadmanager:
  runtimeClassName: ""
```

For production, inject `REDIS_PASSWORD` with `extraEnv` and `secretKeyRef` instead of plain text in values files.

## Helm install

From the repository root:

```bash
helm upgrade --install agentcube ./manifests/charts/base \
  --namespace agentcube --create-namespace \
  -f my-values.yaml
```

Verify:

```bash
kubectl -n agentcube get deploy,svc
```

## Health checks

| Service | Endpoints |
|---------|-----------|
| Workload Manager | `GET /health`, `/healthz`, `/readyz` |
| Router | `GET /health/live`, `GET /health/ready`, `/healthz`, `/readyz` |

Port-forward for local debugging:

```bash
kubectl -n agentcube port-forward svc/agentcube-router 8080:8080
```

## What’s next

- Define an `AgentRuntime` or `CodeInterpreter` resource for your agent image
- Follow the [First agent](./tutorials/first-agent.md) tutorial
- Read [Architecture → Security](./architecture/security.md) before exposing the Router publicly
