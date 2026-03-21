# AgentCube

AgentCube is a [Volcano](https://github.com/volcano-sh/volcano) subproject that brings **scheduling and lifecycle management** for **AI agent workloads** to Kubernetes. It provides a control plane (router, workload manager), CRDs for agent runtimes and code interpreters, and SDKs so platforms can provision sandboxes, route traffic, and enforce session policy consistently on-cluster.

## Features

- **Custom resources** — `AgentRuntime` and `CodeInterpreter` (`runtime.agentcube.volcano.sh/v1alpha1`) describe reusable runtime templates and managed interpreter pools with HTTP(S) routing metadata, pod templates, and session timeouts.
- **Workload manager** — Reconciles sandbox CRs from the broader agents ecosystem (`agents.x-k8s.io`, `extensions.agents.x-k8s.io`) together with AgentCube runtime APIs; exposes health and admin HTTP APIs.
- **Router** — Edge HTTP router with liveness/readiness endpoints, suitable for fronting agent data-plane traffic.
- **Helm chart** — Base chart under `manifests/charts/base` for router, workload manager, optional Volcano agent scheduler (development profile), and RBAC.
- **SDKs** — Python SDK under `sdk-python` for control-plane and data-plane interactions; Go APIs under `pkg/` with generated clients via `hack/update-codegen.sh`.

## Repository layout

| Path | Purpose |
|------|---------|
| `cmd/` | `workload-manager`, `router`, `picod`, `agentd`, CLI entrypoints |
| `pkg/` | Controllers, router, stores, API types |
| `manifests/charts/base` | Helm chart + CRD stubs |
| `docker/` | Production-oriented multi-stage `Dockerfile`s |
| `sdk-python/` | Python package |
| `docs/` | User-facing documentation |
| `hack/` | Codegen and boilerplate scripts |

## Getting started

See [docs/getting-started.md](docs/getting-started.md) for prerequisites, installing CRDs, and deploying the Helm chart.

### Quick local build

```bash
make deps
make build-all
```

### Images

```bash
make docker-build HUB=ghcr.io/volcano-sh TAG=latest
```

## Contributing

Contributions welcome. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) and the standard Kubernetes [OWNERS](OWNERS) workflow expectations for reviewers and approvers.

## License

Apache License 2.0. See [LICENSE](LICENSE).
