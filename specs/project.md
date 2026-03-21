# AgentCube — OpenSpec Project Context

> Source: [github.com/ShijunDeng/agentcube](https://github.com/ShijunDeng/agentcube)
> Generated: 2026-03-21 (from source tree reverse-engineering)

## Purpose

AgentCube is a Kubernetes-native sandbox orchestration platform for AI agents.
It provisions isolated sandbox pods on demand, routes HTTP traffic to them through
session-aware proxies, and manages their lifecycle (creation, expiry, idle cleanup).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language (server) | Go 1.24, module `github.com/volcano-sh/agentcube` |
| Language (CLI/SDK) | Python ≥3.10 |
| HTTP framework | Gin (Go), Typer (Python CLI), FastAPI (example) |
| Kubernetes | CRDs (`runtime.agentcube.volcano.sh/v1alpha1`), controller-runtime, `sigs.k8s.io/agent-sandbox` |
| Storage | Redis (go-redis/v9), Valkey (valkey-go) |
| Auth | JWT RS256 (golang-jwt/v5), K8s TokenReview |
| Packaging | Helm 3, multi-stage Docker, GitHub Actions CI/CD |
| Docs | Docusaurus 3.x |

## Architecture

```
Client / SDK / CLI
  → Router (Deployment :8080)
     ↔ Redis/Valkey (session store)
     → WorkloadManager (Service :8080)
        ↔ Redis/Valkey
        → K8s API: CRDs, Sandbox, Pod, Secret, TokenReview
  Sandbox Pods (with optional PicoD daemon)
  Agentd (idle cleanup controller)
  Optional: Volcano vc-agent-scheduler
```

## Conventions

- Go packages under `pkg/`, binaries under `cmd/`
- Python CLI at `cmd/cli/`, SDK at `sdk-python/`
- JSON tags use camelCase; Go structs use PascalCase
- K8s resources use `runtime.agentcube.volcano.sh` API group
- Normative language: SHALL = mandatory, SHOULD = recommended, MAY = optional
