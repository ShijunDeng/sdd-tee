# AR-032 — Dockerfile 多阶段构建 (3 images)

## Purpose

Provide three multi-stage Dockerfiles to build production-ready container images for AgentCube's core binaries: Workload Manager, Router, and picod. Each Dockerfile separates the Go compilation stage from the minimal runtime stage, reducing final image size, eliminating build-time dependencies from production images, and running binaries as non-root users where security permits. The images are built via Makefile targets and loaded into Kind for E2E testing or pushed to `ghcr.io/volcano-sh` for production deployment.

## Scope

### In scope

| Item | Detail |
|------|--------|
| **`docker/Dockerfile`** | Workload Manager multi-stage build (golang:1.24.9-alpine → alpine:3.19) |
| **`docker/Dockerfile.router`** | Router multi-stage build (golang:1.24.9-alpine → alpine:3.19) |
| **`docker/Dockerfile.picod`** | picod multi-stage build (golang:1.24.4 → ubuntu:24.04) |
| **Makefile targets** | `docker-build`, `docker-build-router`, `docker-build-picod` and their buildx/push/kind-load variants |
| **Build context** | Repository root (all three Dockerfiles use `.` as context) |
| **Multi-arch support** | `docker-buildx` targets for linux/amd64 and linux/arm64 |
| **Non-root runtime** | `apiserver` (UID 1000) for workloadmanager, `router` (UID 1000) for router |
| **Security hardening** | `CGO_ENABLED=0`, `-ldflags="-s -w"`, minimal base images, ca-certificates only |

### Out of scope

- `example/pcap-analyzer/Dockerfile` (separate AR, Python-based example)
- CI/CD pipeline integration for automated image push (covered by ci-cd spec)
- Helm chart image tag management (handled by `values.yaml`)
- Docker Compose orchestration (not required for AgentCube deployment model)
- Image scanning / SBOM generation
- Runtime user for picod (runs as root by design — requires `chattr` on pubkey and sandbox permissions)

## Design

### File layout

| File | Role |
|------|------|
| `docker/Dockerfile` | Workload Manager: 2-stage build, outputs `workloadmanager` binary |
| `docker/Dockerfile.router` | Router: 2-stage build, outputs `agentcube-router` binary |
| `docker/Dockerfile.picod` | picod: 2-stage build, outputs `picod` binary |

### `docker/Dockerfile` (Workload Manager)

```dockerfile
# Build stage
FROM golang:1.24.9-alpine AS builder
WORKDIR /workspace
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/ cmd/
COPY pkg/ pkg/
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -ldflags="-s -w" -o workloadmanager ./cmd/workload-manager

# Runtime stage
FROM alpine:3.19
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /workspace/workloadmanager /app/workloadmanager
RUN adduser -D -u 1000 apiserver
USER apiserver
EXPOSE 8080
ENTRYPOINT ["/app/workloadmanager"]
CMD ["--port=8080"]
```

| Stage | Detail |
|-------|--------|
| builder | `golang:1.24.9-alpine`; copies only `go.mod`, `go.sum`, `cmd/`, `pkg/`; BuildKit cache mount for `go build`; `CGO_ENABLED=0` for static binary; `-ldflags="-s -w"` strips debug symbols |
| runtime | `alpine:3.19`; only `ca-certificates` installed; binary copied from builder; non-root user `apiserver` UID 1000; exposes 8080 |

Build args: `TARGETOS=linux` (default), `TARGETARCH` (set by buildx platform).

### `docker/Dockerfile.router`

```dockerfile
# Build stage
FROM golang:1.24.9-alpine AS builder
WORKDIR /workspace
COPY go.mod go.sum ./
RUN go mod download
COPY cmd/ cmd/
COPY pkg/ pkg/
COPY client-go/ client-go/
RUN --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} \
    go build -ldflags="-s -w" -o agentcube-router ./cmd/router

# Runtime stage
FROM alpine:3.19
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /workspace/agentcube-router /app/agentcube-router
RUN adduser -D -u 1000 router
USER router
EXPOSE 8080
ENTRYPOINT ["/app/agentcube-router"]
CMD ["--port=8080", "--debug"]
```

| Stage | Detail |
|-------|--------|
| builder | Same as workloadmanager, plus `COPY client-go/ client-go/` (generated Kubernetes clientset); outputs `agentcube-router` from `./cmd/router` |
| runtime | `alpine:3.19`; non-root user `router` UID 1000; default CMD includes `--debug` flag |

### `docker/Dockerfile.picod`

```dockerfile
# Build stage
FROM golang:1.24.4 AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o picod ./cmd/picod

# Runtime stage
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y python3
WORKDIR /root/
COPY --from=builder /app/picod ./picod
# Runs as root: chattr on pubkey + sandbox permissions require elevated privileges
ENTRYPOINT ["./picod"]
```

| Stage | Detail |
|-------|--------|
| builder | `golang:1.24.4` (note: different version from control plane); `COPY . .` copies entire repo (picod is a separate module at repo root); no BuildKit cache mount |
| runtime | `ubuntu:24.04` (not Alpine — requires `python3` for sandbox subprocess execution); runs as root (comment documents rationale) |

### Makefile Docker targets

| Target | Command |
|--------|---------|
| `docker-build` | `$(CONTAINER_TOOL) build -f docker/Dockerfile -t $(WORKLOAD_MANAGER_IMAGE) .` |
| `docker-build-router` | `$(CONTAINER_TOOL) build -f docker/Dockerfile.router -t $(ROUTER_IMAGE) .` |
| `docker-build-picod` | `$(CONTAINER_TOOL) build -f docker/Dockerfile.picod -t $(PICOD_IMAGE) .` |
| `docker-buildx` | `docker buildx build --platform linux/amd64,linux/arm64 -f docker/Dockerfile -t $(HUB)/workloadmanager:$(TAG) .` |
| `docker-buildx-router` | Same pattern for router image |
| `docker-buildx-picod` | Same pattern for picod image |
| `docker-buildx-push` | As above with `--push`; requires `IMAGE_REGISTRY` set |
| `docker-buildx-push-router` | Same for router |
| `docker-buildx-push-picod` | Same for picod |
| `docker-push` | `docker tag` + `docker push` for workloadmanager |
| `docker-push-router` | Same for router |
| `docker-push-picod` | Same for picod |
| `kind-load` | `kind load docker-image $(WORKLOAD_MANAGER_IMAGE) --name $(E2E_CLUSTER_NAME)` |
| `kind-load-router` | Same for router |

### Image characteristics

| Image | Builder base | Runtime base | Binary | User | Port |
|-------|-------------|--------------|--------|------|------|
| workloadmanager | golang:1.24.9-alpine | alpine:3.19 | `workloadmanager` | apiserver (1000) | 8080 |
| agentcube-router | golang:1.24.9-alpine | alpine:3.19 | `agentcube-router` | router (1000) | 8080 |
| picod | golang:1.24.4 | ubuntu:24.04 | `picod` | root | N/A |

## Impact analysis

### Files created

| File | Lines (est.) |
|------|-------------|
| `docker/Dockerfile` | ~18 |
| `docker/Dockerfile.router` | ~20 |
| `docker/Dockerfile.picod` | ~14 |

### Files modified

| File | Change |
|------|--------|
| `Makefile` | Add `docker-build`, `docker-build-router`, `docker-build-picod` targets and variants |

### Dependencies

| Dependency | Usage |
|------------|-------|
| Docker / Podman | Container image build runtime (`CONTAINER_TOOL` variable) |
| BuildKit | Cache mount support in builder stage (`--mount=type=cache`) |
| docker buildx | Multi-arch cross-compilation (`--platform linux/amd64,linux/arm64`) |
| Kind | E2E image loading (`kind load docker-image`) |

### Downstream consumers

| Consumer | Dependency |
|----------|-----------|
| `manifests/charts/base/values.yaml` | References image `repository:tag` for each component |
| `test/e2e/run_e2e.sh` | Expects images built and loaded into Kind cluster |
| GitHub Actions CI | Calls `docker-buildx-push` targets for automated publishing |
| Helm install command | Uses image names from `values.yaml` overrides |

### Breaking change risk

**None**: These are new files. No existing Dockerfiles or build processes are replaced.

### Performance characteristics

- **Build cache efficiency**: `go.mod`/`go.sum` copied before source code — dependency download cached independently of code changes
- **BuildKit cache mount**: `/root/.cache/go-build` persisted across builds, reducing compile time for unchanged packages
- **Final image size**: Alpine runtime (~5-10 MB) vs full golang image (~300+ MB); estimated 95%+ size reduction
- **Multi-arch**: Single `docker-buildx` invocation produces both amd64 and arm64 manifests

### Edge cases handled

1. **Cross-platform build**: `GOOS=${TARGETOS} GOARCH=${TARGETARCH}` build args set by buildx for correct target architecture
2. **Static binary**: `CGO_ENABLED=0` ensures no dynamic library dependencies on Alpine runtime
3. **Symbol stripping**: `-ldflags="-s -w"` removes debug info and symbol table, further reducing binary size
4. **picod root requirement**: Documented in Dockerfile comment; cannot run as non-root due to `chattr` and sandbox permission requirements
5. **Go version divergence**: picod uses golang:1.24.4 (not 1.24.9) — pinned to picod module's tested version

## Alternatives considered

### 1. Single-stage Dockerfiles

**Approach**: Use full `golang` image as runtime, compile and run in the same stage.

**Rejected because**:
- Final image size ~300-500 MB vs ~10 MB for multi-stage (30-50x larger)
- Exposes build toolchain (compiler, linker, source code) in production image — security risk
- Longer pull times for deployment, especially in air-gapped or low-bandwidth environments
- Violates container best practice of minimal runtime images

### 2. Distroless base images (gcr.io/distroless/static)

**Approach**: Use Google's distroless images as runtime base instead of Alpine.

**Rejected because**:
- Distroless `static` has no package manager — cannot install `ca-certificates` or `python3` (required by picod)
- Distroless `base` (Debian-based) is larger than Alpine (~20 MB vs ~5 MB)
- picod requires `python3` at runtime — distroless does not provide it without custom extension
- Alpine provides sufficient minimalism with `apk` for the few required packages
- Workload Manager and Router only need `ca-certificates` — Alpine handles this with negligible overhead

### 3. Shared builder image for all three binaries

**Approach**: Single Dockerfile with multiple builder stages and multiple runtime stages, producing all three binaries from one build.

**Rejected because**:
- Violates single-responsibility: one Dockerfile per deployable artifact is standard practice
- Forces rebuild of all binaries when only one changes (no independent caching)
- picod requires different Go version (1.24.4) and full repo copy (`COPY . .`) — incompatible with control-plane builder
- Helm chart expects separate image repositories (`workloadmanager`, `agentcube-router`, `picod`)
- CI/CD pipelines build and push images independently per component

### 4. Binary-only COPY from pre-built artifacts

**Approach**: CI builds Go binaries on host/runner, Dockerfile only copies pre-compiled binary into runtime image.

**Rejected because**:
- Loses reproducibility: Docker build no longer self-contained — depends on external build environment
- Cross-compilation complexity shifts from Docker build args to CI matrix configuration
- No build cache benefit — every CI run recompiles from scratch
- Developer local builds (`make docker-build`) would require matching Go toolchain on host
- Multi-stage Dockerfile provides identical output with better encapsulation

### 5. Ubuntu runtime for all images (uniformity)

**Approach**: Use `ubuntu:24.04` as runtime base for all three images instead of mixing Alpine and Ubuntu.

**Rejected because**:
- Workload Manager and Router are pure Go static binaries — Ubuntu's glibc, coreutils, and package manager add ~70 MB of unnecessary attack surface
- picod requires Ubuntu for `python3` — this is a genuine dependency, not a preference
- Alpine's musl libc is compatible with `CGO_ENABLED=0` static binaries (no libc needed at runtime)
- Security scanning would flag Ubuntu images for more CVEs due to larger package footprint
- The marginal benefit of base image uniformity does not outweigh the security and size costs