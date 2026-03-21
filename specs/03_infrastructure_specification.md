# AgentCube Infrastructure Specification

> Reverse-engineered from https://github.com/ShijunDeng/agentcube.git
> Generated at: 2026-03-21T03:09:00Z (Stage 1 of SDD Benchmark)

---

## 1. Helm Chart (manifests/charts/base/)

### Values

| Path | Default | Description |
|------|---------|-------------|
| redis.addr | "" | Redis address (required) |
| redis.password | "" | Redis password |
| router.replicas | 1 | Router replicas |
| router.image.repository | ghcr.io/volcano-sh/agentcube-router | |
| router.image.tag | latest | |
| router.service.type | ClusterIP | |
| router.service.port | 8080 | |
| router.rbac.create | false | Enable router RBAC |
| workloadmanager.replicas | 1 | |
| workloadmanager.image.repository | ghcr.io/volcano-sh/workloadmanager | |
| workloadmanager.service.port | 8080 | |
| volcano.scheduler.enabled | false | Optional Volcano scheduler |

### Templates
- workloadmanager.yaml: Deployment + Service
- agentcube-router.yaml: Deployment + Service
- rbac/workloadmanager.yaml: SA + ClusterRole + ClusterRoleBinding
- rbac-router.yaml: Conditional Role + RoleBinding + SA
- volcano-agent-scheduler-development.yaml: Conditional full scheduler stack

## 2. RBAC

### Workload Manager (ClusterRole)
- agents.x-k8s.io: sandboxes (full CRUD)
- extensions.agents.x-k8s.io: sandboxclaims, sandboxtemplates, sandboxwarmpools (full)
- runtime.agentcube.volcano.sh: codeinterpreters (full), agentruntimes (read)
- "": pods (read), secrets (full)
- authentication.k8s.io: tokenreviews (create)

### Router (Optional Role)
- "": secrets (full CRUD) in namespace

## 3. Dockerfiles

| File | Builder | Runtime | Binary | User |
|------|---------|---------|--------|------|
| Dockerfile | golang:1.24.9-alpine | alpine:3.19 | workloadmanager | apiserver(1000) |
| Dockerfile.router | golang:1.24.9-alpine | alpine:3.19 | router | router(1000) |
| Dockerfile.picod | golang:1.24.4 | ubuntu:24.04 | picod | root |

## 4. Makefile Targets

| Category | Targets |
|----------|---------|
| Build | build, build-agentd, build-router, build-all |
| Run | run, run-local, run-router |
| Codegen | gen-crd, generate, gen-client, gen-all, gen-check |
| Test | test, fmt, vet, lint |
| Docker | docker-build[-router\|-picod], docker-buildx[-*], docker-push[-*], kind-load[-*] |
| E2E | e2e, e2e-clean |
| Other | install, build-python-sdk, clean, deps, help |

## 5. CI/CD Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| main.yml | PR → main | Build check |
| build-push-release.yml | Push tags v*.*.* | Push to ghcr.io |
| e2e.yml | PR → main | End-to-end tests |
| lint.yml | PR (Go paths) | golangci-lint |
| codegen-check.yml | PR | gen-check |
| test-coverage.yml | PR | Go test + Codecov |
| python-sdk-tests.yml | PR (sdk-python/) | pytest |
| python-lint.yml | PR | ruff check |
| codespell.yml | PR | Spell check |
| copyright-check.yml | PR | License headers |

## 6. Deployment Architecture

```
Client / SDK
  → Router (Deployment, :8080)
     ↔ Redis (external)
     → Workload Manager (Service :8080)
        ↔ Redis
        → K8s API: CRDs, Sandboxes, Pods, Secrets, TokenReview
  Sandboxes (Pods) with optional PicoD
  Optional: Volcano vc-agent-scheduler
```

Prerequisites: kubernetes-sigs/agent-sandbox CRDs, Redis
