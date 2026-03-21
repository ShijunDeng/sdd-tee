# Getting started with AgentCube

## Prerequisites

- Kubernetes **1.28+** (1.30+ recommended for newer CRD features)
- [`kubectl`](https://kubernetes.io/docs/tasks/tools/) configured for your cluster
- [`helm`](https://helm.sh/docs/intro/install/) 3.14+ (for chart install)
- A **Redis** / Valkey instance reachable from the cluster (for router and workload manager coordination)
- (Optional) [`kind`](https://kind.sigs.k8s.io/) for local clusters and `make kind-load`

## Install CRDs

Apply the API extensions before installing the chart (or use `helm install` with `--skip-crds` only if you manage CRDs separately):

```bash
kubectl apply -f manifests/charts/base/crds/
```

Resources:

- `agentruntimes.runtime.agentcube.volcano.sh` — reusable agent runtime templates (`AgentRuntime`)
- `codeinterpreters.runtime.agentcube.volcano.sh` — managed interpreter pools (`CodeInterpreter`)

CRD YAML under `manifests/charts/base/crds/` is aligned with `pkg/apis/runtime/v1alpha1/types.go` and can be regenerated with controller-gen via `make gen-crd`.

## Configure values

Create a small values file (example `my-values.yaml`):

```yaml
redis:
  addr: redis-master.mystore.svc.cluster.local:6379
  password: "" # prefer extraEnv + secretKeyRef in production

workloadmanager:
  runtimeClassName: kuasar-vmm

router:
  rbac:
    create: true   # if the router needs namespaced Secret read access
```

Never commit real credentials; inject `REDIS_PASSWORD` with `extraEnv` pointing at a Secret.

## Install the Helm chart

```bash
helm upgrade --install agentcube ./manifests/charts/base \
  --namespace agentcube --create-namespace \
  -f my-values.yaml
```

Verify workloads:

```bash
kubectl -n agentcube get deploy,svc
```

## Health endpoints

- **Workload manager**: `GET /health` (and `/healthz`, `/readyz` for compatibility)
- **Router**: `GET /health/live`, `GET /health/ready` (and `/healthz`, `/readyz`)

## Next steps

- Implement or enable controllers that reconcile `AgentRuntime` / `CodeInterpreter` to Pods and Services.
- Wire **Volcano** scheduling if you use `PodGroup` / queueing (`volcano.scheduler.enabled` in chart values is a development-oriented scaffold).
- Run `make e2e` once a cluster and test suite are configured.
