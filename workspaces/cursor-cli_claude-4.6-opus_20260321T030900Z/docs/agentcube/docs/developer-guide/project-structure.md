---
sidebar_position: 2
---

# Project structure

The AgentCube repository groups production code, packaging, and client libraries by concern.

## Top-level layout

| Path | Purpose |
|------|---------|
| `cmd/` | Entrypoints: `workload-manager`, `router`, `picod`, `agentd`, and the Python CLI under `cmd/cli/`. |
| `pkg/` | Shared libraries: API types, controllers, Router, PicoD, Redis store, common utilities. |
| `pkg/apis/runtime/v1alpha1` | `AgentRuntime` and `CodeInterpreter` Go types + kubebuilder annotations. |
| `pkg/apis/agentsandbox/v1alpha1` | Sandbox ecosystem types (`Sandbox`, `SandboxClaims`). |
| `manifests/charts/base` | Helm chart, CRD YAML, Deployment and RBAC templates. |
| `docker/` | Container build definitions (`Dockerfile`, `Dockerfile.router`, `Dockerfile.picod`, …). |
| `sdk-python/` | Installable Python package for control-plane and data-plane clients. |
| `hack/` | Codegen (`update-codegen.sh`), boilerplate, copyright scripts. |
| `docs/` | User docs, design proposals, and this Docusaurus site (`docs/agentcube/`). |
| `.github/workflows/` | CI: Go tests, lint, Python SDK tests, e2e placeholders. |

## Controller code

Reconciliation logic for runtimes and sandboxes lives under `pkg/controller/` and `pkg/workloadmanager/` (including `sandbox_builder.go`, `sandbox_controller.go`, `codeinterpreter_controller.go`, garbage collection, and caching layers).

## Clients

- **Go:** typed clients can be generated via `make gen-client` (see `hack/update-codegen.sh`).
- **Python:** `agentcube` package exposes `CodeInterpreterClient`, data-plane helpers, and HTTP utilities.

When adding a feature, place API changes in `pkg/apis/...`, regenerate CRDs if needed (`make generate`), then update controllers and documentation together.
