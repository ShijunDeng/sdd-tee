---
sidebar_position: 4
---

# Local development

## Go services

Prerequisites: Go toolchain matching `go.mod`, optional `golangci-lint`.

```bash
make deps
make build-all
```

Run binaries directly after build:

```bash
make run-local     # workload manager
make run-router    # router
```

Configure environment variables expected by each binary (Redis address, Kubernetes kubeconfig, namespace, TLS material). Use a local **kind** cluster or a dev namespace on a shared cluster—never point dev controllers at production.

## Code generation

After editing API types under `pkg/apis/`:

```bash
make generate      # CRDs + deepcopy
make gen-client    # typed client-go (requires code-generator on PATH)
```

## Python CLI and SDK

```bash
pip install -e ./cmd/cli
pip install -e ./sdk-python
```

Run the Typer CLI:

```bash
kubectl-agentcube --help
```

## Helm chart iteration

```bash
helm template agentcube ./manifests/charts/base -f my-dev-values.yaml
```

Install to a throwaway namespace and use `kubectl logs` liberally.

## Docusaurus docs

```bash
cd docs/agentcube && npm install && npm run start
```

## Tips

- Enable **verbose** logging flags where available (`--verbose` on CLI, klog verbosity on Go binaries).
- Keep **Redis** reachable from your workstation if running Router/Workload Manager outside the cluster (tunnel or in-cluster Redis with port-forward).
