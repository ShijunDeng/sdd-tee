# AgentCube Infrastructure Specification

This document is derived from the AgentCube reference tree at `/tmp/agentcube-ref`. It describes packaging, Kubernetes manifests, container images, build automation, CI/CD, tests, documentation, and root configuration as present in that snapshot.

---

## 1. Helm chart (`manifests/charts/base/`)

### 1.1 `Chart.yaml`

| Field | Value |
|--------|--------|
| `apiVersion` | `v1` |
| `name` | `agentcube` |
| `description` | `A Helm chart for AgentCube` |
| `version` | `0.1.0` |
| `appVersion` | `1.0.0` |

### 1.2 `values.yaml` — full value tree

| Key path | Type | Default | Notes / description (from comments or usage) |
|----------|------|---------|------------------------------------------------|
| `imagePullSecrets` | `array` | `[]` | Passed into pod specs via `toYaml` where supported. |
| `nameOverride` | `string` | `""` | Standard Helm override (not referenced in provided templates). |
| `fullnameOverride` | `string` | `""` | Standard Helm override (not referenced in provided templates). |
| `redis.addr` | `string` | `""` | **Comment:** must be provided at install; used as `REDIS_ADDR` env for router and workloadmanager. |
| `redis.password` | `string` | `""` | **Comment:** must be provided at install; used as `REDIS_PASSWORD` env. |
| `router.replicas` | `int` | `1` | Router Deployment replicas. |
| `router.image.repository` | `string` | `ghcr.io/volcano-sh/agentcube-router` | Container image repo. |
| `router.image.pullPolicy` | `string` | `IfNotPresent` | Image pull policy. |
| `router.image.tag` | `string` | `"latest"` | Image tag. |
| `router.service.type` | `string` | `ClusterIP` | Kubernetes Service type. |
| `router.service.port` | `int` | `8080` | Service port. |
| `router.service.targetPort` | `int` | `8080` | Container port / probe port. |
| `router.resources.limits.cpu` | `string` | `500m` | — |
| `router.resources.limits.memory` | `string` | `512Mi` | — |
| `router.resources.requests.cpu` | `string` | `100m` | — |
| `router.resources.requests.memory` | `string` | `128Mi` | — |
| `router.config` | `object` | `{}` | **Not referenced** in the templates under review. |
| `router.extraEnv` | `array` | `[]` | Extra env vars merged into router container (Helm `toYaml`). |
| `router.serviceAccountName` | `string` | `""` | If non-empty, sets `spec.template.spec.serviceAccountName` on router Deployment. |
| `router.rbac.create` | `bool` | `false` | When `true`, renders `rbac-router.yaml` (SA + Role + RoleBinding). |
| `workloadmanager.replicas` | `int` | `1` | Workloadmanager Deployment replicas. |
| `workloadmanager.image.repository` | `string` | `ghcr.io/volcano-sh/workloadmanager` | Container image repo. |
| `workloadmanager.image.pullPolicy` | `string` | `IfNotPresent` | Image pull policy. |
| `workloadmanager.image.tag` | `string` | `"latest"` | Image tag. |
| `workloadmanager.service.type` | `string` | `ClusterIP` | Kubernetes Service type. |
| `workloadmanager.service.port` | `int` | `8080` | Used as Service port, container port, and `--port` arg. |
| `workloadmanager.resources.limits.cpu` | `string` | `500m` | — |
| `workloadmanager.resources.limits.memory` | `string` | `512Mi` | — |
| `workloadmanager.resources.requests.cpu` | `string` | `100m` | — |
| `workloadmanager.resources.requests.memory` | `string` | `128Mi` | — |
| `workloadmanager.extraEnv` | `array` | `[]` | Extra env vars merged into workloadmanager container. |
| `volcano.scheduler.enabled` | `bool` | `false` | Gates entire `volcano-agent-scheduler-development.yaml` template block. |
| `volcano.scheduler.replicas` | `int` | `1` | Volcano agent scheduler Deployment replicas. |
| `volcano.scheduler.image.repository` | `string` | `ghcr.io/volcano-sh/vc-agent-scheduler` | Image repo. |
| `volcano.scheduler.image.pullPolicy` | `string` | `IfNotPresent` | Image pull policy. |
| `volcano.scheduler.image.tag` | `string` | `"latest"` | Image tag. |

### 1.3 CRDs shipped with the chart (`charts/base/crds/`)

Helm 3 installs manifests in `crds/` before other resources.

| File | CRD `metadata.name` |
|------|---------------------|
| `runtime.agentcube.volcano.sh_codeinterpreters.yaml` | `codeinterpreters.runtime.agentcube.volcano.sh` |
| `runtime.agentcube.volcano.sh_agentruntimes.yaml` | `agentruntimes.runtime.agentcube.volcano.sh` |

(See **Section 2** for CRD details.)

### 1.4 Templates — resources and conditionals

#### `templates/workloadmanager.yaml`

| Resource | Name | Conditionals / notes |
|----------|------|----------------------|
| `Deployment` | `workloadmanager` | `{{- with .Values.imagePullSecrets }}` → optional `imagePullSecrets`. |
| `Service` | `workloadmanager` | None. |

**Fixed / wired fields:**

- `metadata.namespace`: `{{ .Release.Namespace }}`
- `serviceAccountName`: hardcoded `workloadmanager` (SA defined in RBAC template).
- Env: `AGENTCUBE_NAMESPACE` from `fieldRef` `metadata.namespace`; `REDIS_PASSWORD`, `REDIS_ADDR` from values.
- Args: `--port={{ .Values.workloadmanager.service.port }}`, `--runtime-class-name=` (empty string literal).
- Probes: HTTP GET `/health` on workloadmanager service port; liveness `initialDelaySeconds: 10`, `periodSeconds: 10`; readiness `initialDelaySeconds: 5`, `periodSeconds: 5`.
- Service: `targetPort` equals `.Values.workloadmanager.service.port` (same as `port` in template).

#### `templates/agentcube-router.yaml`

| Resource | Name | Conditionals / notes |
|----------|------|----------------------|
| `Deployment` | `agentcube-router` | `{{- if .Values.router.serviceAccountName }}` → optional `serviceAccountName`; `{{- with .Values.imagePullSecrets }}`. |
| `Service` | `agentcube-router` | None. |

**Fixed / wired fields:**

- `WORKLOAD_MANAGER_URL`: `http://workloadmanager.{{ .Release.Namespace }}.svc.cluster.local:{{ .Values.workloadmanager.service.port }}`
- Args: `--port={{ .Values.router.service.targetPort }}`, `--debug`
- Probes: `/health/live` and `/health/ready` on `targetPort`; `initialDelaySeconds: 1`, `periodSeconds: 2`.

#### `templates/rbac-router.yaml`

| Resource | Condition |
|----------|-----------|
| `ServiceAccount`, `Role`, `RoleBinding` | `{{- if .Values.router.rbac.create }}` |

**Name logic:** `{{ .Values.router.serviceAccountName | default "agentcube-router" }}` for SA, Role, RoleBinding names and subject name.

#### `templates/rbac/workloadmanager.yaml`

Always rendered (no `if`):

| Resource | Name |
|----------|------|
| `ServiceAccount` | `workloadmanager` |
| `ClusterRole` | `workloadmanager` |
| `ClusterRoleBinding` | `workloadmanager` |

Subject: SA `workloadmanager` in `{{ .Release.Namespace }}`.

#### `templates/volcano-agent-scheduler-development.yaml`

| Condition | Content |
|-----------|---------|
| `{{- if .Values.volcano.scheduler.enabled }}` | Full block (see RBAC table below); otherwise nothing. |

**Resources when enabled (in order):** `ServiceAccount`, `ConfigMap`, `ClusterRole`, `ClusterRoleBinding`, `Service`, `Deployment`.

**Embedded ConfigMap data** (`agent-scheduler.conf`):

```text
actions: "allocate"
tiers:
- plugins:
  - name: predicates
  - name: nodeorder
```

**Deployment highlights:** `priorityClassName: system-cluster-critical`, `runAsUser: 1000`, `runAsNonRoot: true`, `seccompProfile: RuntimeDefault`, capabilities `DAC_OVERRIDE` add / `ALL` drop, fixed scheduler args including `--scheduler-name=agent-scheduler`, metrics on 8080, etc.

### 1.5 RBAC rules (exact apiGroups / resources / verbs)

#### Router `Role` (`rbac-router.yaml`) — namespace-scoped

| apiGroups | resources | verbs |
|-----------|-----------|-------|
| `""` | `secrets` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |

#### Workloadmanager `ClusterRole` (`rbac/workloadmanager.yaml`)

| apiGroups | resources | verbs |
|-----------|-----------|-------|
| `agents.x-k8s.io` | `sandboxes` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
| `extensions.agents.x-k8s.io` | `sandboxclaims` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
| `extensions.agents.x-k8s.io` | `sandboxtemplates` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
| `extensions.agents.x-k8s.io` | `sandboxwarmpools` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
| `extensions.agents.x-k8s.io` | `sandboxwarmpools/status` | `get`, `update`, `patch` |
| `runtime.agentcube.volcano.sh` | `codeinterpreters` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |
| `runtime.agentcube.volcano.sh` | `codeinterpreters/status` | `get`, `update`, `patch` |
| `runtime.agentcube.volcano.sh` | `codeinterpreters/finalizers` | `update` |
| `runtime.agentcube.volcano.sh` | `agentruntimes` | `get`, `list`, `watch` |
| `runtime.agentcube.volcano.sh` | `agentruntimes/status` | `update`, `patch` |
| `""` | `pods` | `get`, `list`, `watch` |
| `authentication.k8s.io` | `tokenreviews` | `create` |
| `""` | `secrets` | `get`, `list`, `watch`, `create`, `update`, `patch`, `delete` |

#### Volcano agent scheduler `ClusterRole` (only if `volcano.scheduler.enabled`)

| apiGroups | resources | verbs |
|-----------|-----------|-------|
| `apiextensions.k8s.io` | `customresourcedefinitions` | `create`, `get`, `list`, `watch`, `delete` |
| `""` | `events` | `create`, `list`, `watch`, `update`, `patch` |
| `""` | `pods` | `get`, `list`, `watch`, `patch`, `delete` |
| `""` | `pods/status` | `update` |
| `""` | `pods/binding` | `create` |
| `""` | `persistentvolumeclaims` | `list`, `watch`, `update` |
| `""` | `persistentvolumes` | `list`, `watch`, `update` |
| `""` | `namespaces`, `services`, `replicationcontrollers` | `list`, `watch`, `get` |
| `""` | `resourcequotas` | `list`, `watch` |
| `""` | `nodes` | `get`, `list`, `watch`, `update`, `patch` |
| `storage.k8s.io` | `storageclasses`, `csinodes`, `csidrivers`, `csistoragecapacities`, `volumeattachments` | `list`, `watch` |
| `policy` | `poddisruptionbudgets` | `list`, `watch` |
| `scheduling.k8s.io` | `priorityclasses` | `get`, `list`, `watch` |
| `scheduling.incubator.k8s.io`, `scheduling.volcano.sh` | `podgroups` | `list`, `watch`, `update` |
| `""` | `configmaps` | `get`, `list`, `watch`, `create`, `delete`, `update` |
| `apps` | `daemonsets`, `replicasets`, `statefulsets` | `list`, `watch`, `get` |
| `coordination.k8s.io` | `leases` | `get`, `create`, `update`, `watch` |
| `resource.k8s.io` | `resourceclaims` | `get`, `list`, `watch`, `create`, `update`, `patch` |
| `resource.k8s.io` | `resourceclaims/status` | `update` |
| `resource.k8s.io` | `deviceclasses`, `resourceslices` | `get`, `list`, `watch`, `create` |
| `shard.volcano.sh` | `nodeshards` | `list`, `watch`, `get`, `update` |

### 1.6 `manifests/OWNERS`

Kubernetes-style OWNERS file: reviewers `t2wang`, `acsoto`; approvers `t2wang`.

---

## 2. CRD manifests (`manifests/charts/base/crds/`)

### 2.1 Common metadata

| Property | CodeInterpreter CRD | AgentRuntime CRD |
|----------|----------------------|------------------|
| `apiVersion` | `apiextensions.k8s.io/v1` | `apiextensions.k8s.io/v1` |
| `kind` | `CustomResourceDefinition` | `CustomResourceDefinition` |
| `metadata.annotations.controller-gen.kubebuilder.io/version` | `v0.17.2` | `v0.17.2` |
| `spec.group` | `runtime.agentcube.volcano.sh` | `runtime.agentcube.volcano.sh` |
| `spec.scope` | `Namespaced` | `Namespaced` |
| `spec.names.kind` | `CodeInterpreter` | `AgentRuntime` |
| `spec.names.listKind` | `CodeInterpreterList` | `AgentRuntimeList` |
| `spec.names.plural` | `codeinterpreters` | `agentruntimes` |
| `spec.names.singular` | `codeinterpreter` | `agentruntime` |
| Version name | `v1alpha1` | `v1alpha1` |
| `served` / `storage` | `true` / `true` | `true` / `true` |
| `subresources` | `status: {}` | `status: {}` |
| Additional printer columns | `Age` → `.metadata.creationTimestamp` (`date`) | Same |

### 2.2 `CodeInterpreter` (`runtime.agentcube.volcano.sh_codeinterpreters.yaml`) — schema summary

- **Root OpenAPI:** top-level object requires `spec`.
- **`spec` required field:** `template` (container template for sandbox).
- **Notable `spec` properties:**
  - `authMode` (`string`, enum `picod` | `none`, **default:** `picod`)
  - `maxSessionDuration` (`string`, **default:** `8h`)
  - `sessionTimeout` (`string`, **default:** `15m`)
  - `ports` (`array` of port objects; items require `port`, `protocol`; `protocol` enum `HTTP`/`HTTPS`, default `HTTP`; optional `name`, `pathPrefix`)
  - `template` (`object`): image, command/args, env, resources, labels/annotations, `imagePullPolicy`, `imagePullSecrets`, `runtimeClassName`, etc.
  - `warmPoolSize` (`integer`, int32 format, optional)
- **`status`:** `conditions` (standard condition shape), `ready` (`boolean`).

### 2.3 `AgentRuntime` (`runtime.agentcube.volcano.sh_agentruntimes.yaml`) — schema summary

- **File size:** very large OpenAPI schema (embedded full `PodSpec` under `spec.podTemplate.spec`).
- **Root OpenAPI:** requires `spec`.
- **`spec` required fields (explicit in CRD):** `maxSessionDuration`, `podTemplate`, `sessionTimeout`, `targetPort`
- **Notable `spec` properties:**
  - `maxSessionDuration` (`string`, **default:** `8h`)
  - `sessionTimeout` (`string`, **default:** `15m`)
  - `targetPort` (`array` of `TargetPort`: required `port`, `protocol`; same HTTP/HTTPS enum/default as CodeInterpreter)
  - `podTemplate` (`object`): `annotations`, `labels`, `spec` — where inner `spec` is a full Kubernetes `PodSpec` schema; **`podTemplate.spec` requires `containers`** per CRD.
- **`status`:** `conditions` (describes known types including `Accepted`); optional structure beyond conditions per generated schema.

---

## 3. Docker (`docker/`)

### 3.1 `Dockerfile` (workloadmanager)

| Aspect | Value |
|--------|--------|
| **Builder stage image** | `golang:1.24.9-alpine` |
| **Build args** | `TARGETOS=linux`, `TARGETARCH` (unset in file; supplied by buildx) |
| **WORKDIR** | `/workspace` |
| **COPY** | `go.mod`, `go.sum`; then `cmd/`, `pkg/` |
| **Build** | `CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH}` → `go build -ldflags="-s -w" -o workloadmanager ./cmd/workload-manager` (with cache mounts for mod and build cache) |
| **Runtime image** | `alpine:3.19` |
| **Runtime packages** | `ca-certificates` (`apk`) |
| **Runtime WORKDIR** | `/app` |
| **COPY from builder** | `/workspace/workloadmanager` → `/app/workloadmanager` |
| **User** | `apiserver` (uid `1000`, `adduser -D`) |
| **EXPOSE** | `8080` |
| **ENTRYPOINT** | `["/app/workloadmanager"]` |
| **CMD** | `["--port=8080"]` |

### 3.2 `Dockerfile.router`

| Aspect | Value |
|--------|--------|
| **Builder** | Same pattern as workloadmanager (`golang:1.24.9-alpine`, cache mounts) |
| **COPY** | `go.mod`, `go.sum`; `cmd/`, `pkg/`, `client-go/` |
| **Binary** | `go build ... -o agentcube-router ./cmd/router` |
| **Runtime** | `alpine:3.19`, `ca-certificates`, `WORKDIR /app` |
| **User** | `router` (uid `1000`) |
| **EXPOSE** | `8080` |
| **ENTRYPOINT** | `["/app/agentcube-router"]` |
| **CMD** | `["--port=8080", "--debug"]` |

### 3.3 `Dockerfile.picod`

| Aspect | Value |
|--------|--------|
| **Builder image** | `golang:1.24.4` (Debian-based, not Alpine) |
| **COPY** | `go.mod`, `go.sum` then **entire repo** `COPY . .` |
| **Binary** | `go build ... -o picod ./cmd/picod` |
| **Runtime image** | `ubuntu:24.04` |
| **Packages** | `python3` via `apt-get` |
| **WORKDIR** | `/root/` |
| **User** | **root** (comment: `chattr` on pubkey + sandbox execution) |
| **EXPOSE** | *(none declared)* |
| **ENTRYPOINT** | `["./picod"]` |
| **CMD** | *(none; uses entrypoint only)* |

### 3.4 `docker/OWNERS`

Reviewers: `YaoZengzeng`, `hzxuzhonghu`, `tjucoder`, `VanderChen`; approvers: `hzxuzhonghu`, `kevin-wangzefeng`.

---

## 4. Makefile (`/tmp/agentcube-ref/Makefile`)

### 4.1 Global variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `HUB` | `ghcr.io/volcano-sh` | Documented image URL prefix (not heavily used in shown targets). |
| `TAG` | `latest` | Tag default. |
| `PROJECT_DIR` | auto | Repo root. |
| `GOBIN` | from `go env` | Go binary install path. |
| `CONTAINER_TOOL` | `docker` | Comment only; recipes use `docker` directly. |
| `SHELL` | `/usr/bin/env bash -o pipefail` | Bash with strict pipefail. |
| `LOCALBIN` | `$(shell pwd)/bin` | Local tool binaries. |
| `CONTROLLER_GEN` | `$(LOCALBIN)/controller-gen` | CRD / object generation. |
| `GOLANGCI_LINT` | `$(LOCALBIN)/golangci-lint` | Linter binary. |
| `CONTROLLER_TOOLS_VERSION` | `v0.17.2` | controller-gen version. |
| `GOLANGCI_LINT_VERSION` | `v1.64.1` | golangci-lint version. |
| `WORKLOAD_MANAGER_IMAGE` | `workloadmanager:latest` | Docker image name for WM. |
| `ROUTER_IMAGE` | `agentcube-router:latest` | Docker image for router. |
| `PICOD_IMAGE` | `picod:latest` | Docker image for picod. |
| `IMAGE_REGISTRY` | `""` | Required for push targets. |
| `E2E_CLUSTER_NAME` | `agentcube-e2e` | Kind cluster name for e2e. |
| `AGENT_SANDBOX_REPO` | `https://github.com/kubernetes-sigs/agent-sandbox.git` | *(Declared; e2e script uses release URLs instead.)* |
| `AGENT_SANDBOX_VERSION` | `main` | Makefile default; **`test/e2e/run_e2e.sh` overrides to `v0.1.1` when not set in environment.** |

### 4.2 Targets by category

#### General

| Target | Description | Key variables |
|--------|-------------|----------------|
| `all` | Alias for `build` | — |
| `help` | Print categorized help from `##` / `##@` comments | `MAKEFILE_LIST` |

#### Codegen

| Target | Description | Key variables / commands |
|--------|-------------|---------------------------|
| `controller-gen` | Ensure local `controller-gen` | `go-install-tool` macro |
| `gen-crd` | Generate CRDs to `manifests/charts/base/crds` | `CONTROLLER_GEN`, paths `./pkg/apis/runtime/v1alpha1/...` |
| `generate` | DeepCopy + `go mod tidy` | `CONTROLLER_GEN`, `hack/boilerplate.go.txt`, `./pkg/apis/...` |
| `gen-client` | Run `hack/update-codegen.sh`, `go mod tidy` | — |
| `gen-all` | `generate` + `gen-client` | — |
| `gen-check` | `gen-all` then `git diff --exit-code` | — |

#### Build (Go)

| Target | Description | Notes |
|--------|-------------|-------|
| `build` | Build `bin/workloadmanager` | Depends on `generate` |
| `build-agentd` | Build `bin/agentd` | Depends on `generate` |
| `build-router` | Build `bin/agentcube-router` | Depends on `generate` |
| `build-all` | `build` + `build-agentd` + `build-router` | — |

#### Run (dev)

| Target | Description |
|--------|-------------|
| `run` | `go run ./cmd/workload-manager/main.go --port=8080 --ssh-username=sandbox --ssh-port=22` |
| `run-local` | Same with `--kubeconfig=${HOME}/.kube/config` |
| `run-router` | `go run ./cmd/router/main.go --port=8080 --debug` |

#### Test / quality

| Target | Description |
|--------|-------------|
| `test` | `go test -v ./...` |
| `fmt` | `go fmt ./...` |
| `vet` | `go vet ./...` |
| `lint` | `golangci-lint run ./...` (needs `golangci-lint` target) |
| `gen-copyright` | `hack/update-copyright.sh` |

#### Maintenance

| Target | Description |
|--------|-------------|
| `clean` | Remove `bin/`, root binaries `workloadmanager`, `agentd`, `agentcube-router` |
| `deps` | `go mod download` + `go mod tidy` |
| `update-deps` | `go get -u ./...` + `go mod tidy` |
| `install` | `build` then `sudo cp bin/workloadmanager /usr/local/bin/` |

#### Docker / registry / kind

| Target | Description |
|--------|-------------|
| `docker-build` | `docker build -f docker/Dockerfile -t $(WORKLOAD_MANAGER_IMAGE) .` |
| `docker-buildx` | buildx multi-platform `linux/amd64,linux/arm64` for workloadmanager |
| `docker-buildx-push` | Fails if `IMAGE_REGISTRY` empty; buildx `--push` |
| `docker-push` | `docker-build`, tag/push to `$(IMAGE_REGISTRY)/$(WORKLOAD_MANAGER_IMAGE)` |
| `kind-load` | `kind load docker-image $(WORKLOAD_MANAGER_IMAGE)` |
| `docker-build-router` | `docker build -f docker/Dockerfile.router -t $(ROUTER_IMAGE) .` |
| `docker-buildx-router` | Multi-arch router image |
| `docker-buildx-push-router` | Push router (requires `IMAGE_REGISTRY`) |
| `docker-push-router` | Tag + push router |
| `kind-load-router` | Load router image into kind |
| `docker-build-picod` | `docker build -f docker/Dockerfile.picod -t $(PICOD_IMAGE) .` |
| `docker-buildx-picod` | Multi-arch picod |
| `docker-buildx-push-picod` | Push picod |
| `docker-push-picod` | Tag + push picod |

#### E2E / Python SDK

| Target | Description |
|--------|-------------|
| `e2e` | `./test/e2e/run_e2e.sh` |
| `e2e-clean` | `kind delete cluster --name $(E2E_CLUSTER_NAME)`; `rm -rf /tmp/agent-sandbox` |
| `build-python-sdk` | Copy `LICENSE` → `sdk-python/LICENSE`, `python3 -m build` in `sdk-python`, remove copied LICENSE |

---

## 5. CI/CD (`.github/workflows/`)

### 5.1 Workflow summary table

| File | Triggers | Jobs | Main steps / artifacts |
|------|----------|------|-------------------------|
| `main.yml` | `pull_request` → `main`, `release-*` | `build` | Checkout, Docker Buildx setup, `make docker-build` |
| `e2e.yml` | `pull_request` → `main`, `release-*` | `e2e-test` | Checkout, Go 1.23, `helm/kind-action@v1` **install_only**, `make e2e` with `ARTIFACTS_PATH=${{ github.workspace }}/e2e-logs`, upload artifact on **failure**, `make e2e-clean` **always** |
| `build-push-release.yml` | `push` → `main`; tags `v*.*.*`, `v*.*.*-*` | `build-and-push` | Go 1.24.4, Buildx, login `ghcr.io`, set `TAG` from tag or `latest`, `make docker-buildx-push` / `-router` / `-picod` with `IMAGE_REGISTRY=ghcr.io/${{ github.repository_owner }}` |
| `lint.yml` | `pull_request` → `main`, `release-*` | `golangci` | paths-filter for Go files; Go 1.24; `make lint` |
| `codegen-check.yml` | `pull_request` → `main`, `release-*` | `codegen-check` | paths-filter `pkg/apis`, `hack`, workflows, `Makefile`; Go 1.24.4; `make gen-check` |
| `test-coverage.yml` | `pull_request`, `merge_group`, `workflow_call` | `coverage` | paths-filter; optional free-disk-space; Go 1.24; `go test -race -v -coverprofile=coverage.out -coverpkg=./pkg/... ./pkg/...`; Codecov upload; artifact `go-coverage` |
| `codespell.yml` | `pull_request` → `main`, `release-*` | `codespell` | Temporarily removes `pyproject.toml`, `package-lock.json`, `package.json` copies; `codespell` with skip/ignore lists; restores files |
| `python-sdk-tests.yml` | `pull_request`, `merge_group` | `python-sdk-tests` | paths-filter `sdk-python/**`; Python 3.12; `pip install -e .` in `sdk-python`; `pytest tests/ -v` |
| `python-lint.yml` | `pull_request` → `main`, `release-*` | `python_lint` | paths-filter CLI/sdk/example/test/py; Python 3.10; `ruff check . --config pyproject.toml` |
| `copyright-check.yml` | `pull_request` → `main`, `release-*` | `build` | paths-filter excluding md/svg/png/docs/.github; install `moreutils` (`sponge`); `make gen-copyright`; `git diff --exit-code` |
| `workflows-approve.yml` | `pull_request_target` labeled/synchronize → `main`, `release-**` | `approve` | First-time contributor check; if not first-time or label `ok-to-test`, approve workflow runs stuck in `action_required` |
| `dify-plugin-publish.yml` | `push` tags `dify-plugin/v*` | `publish` | Download dify-plugin CLI 0.0.6, `yq` 4.40.5; package `integrations/dify-plugin`; checkout `author/dify-plugins` with `PLUGIN_ACTION`; open PR to `langgenius/dify-plugins` |

### 5.2 Matrices

No job matrices are defined in the workflows above; parallelism is via separate jobs/workflows only.

### 5.3 Notable permissions / secrets

| Workflow | Permissions / secrets |
|----------|------------------------|
| `lint.yml` | `contents: read`, `pull-requests: read` |
| `workflows-approve.yml` | Job `approve`: `actions: write`; uses `GITHUB_TOKEN` |
| `test-coverage.yml` | Optional `CODECOV_TOKEN` (via `workflow_call` or repo secret) |
| `dify-plugin-publish.yml` | `secrets.PLUGIN_ACTION` for cross-repo checkout/PR |

---

## 6. Tests (`test/`)

### 6.1 Layout

| Path | Role |
|------|------|
| `test/e2e/run_e2e.sh` | Primary orchestration: kind, agent-sandbox manifests, image build/load, Redis, Helm install, CR samples, port-forwards, Go + Python tests, log collection on failure |
| `test/e2e/e2e_test.go` | Go E2E tests (AgentRuntime invocation, errors, TTL); uses client-go, controller-runtime, agent-sandbox APIs |
| `test/e2e/test_codeinterpreter.py` | Python SDK E2E (`CodeInterpreterClient`) |
| `test/e2e/echo_agent.yaml` | Sample `AgentRuntime` |
| `test/e2e/e2e_code_interpreter.yaml` | Sample `CodeInterpreter` in `agentcube` namespace |
| `test/e2e/e2e_code_interpreter_warmpool.yaml` | `CodeInterpreter` with `warmPoolSize: 2` in `default` namespace |
| `test/e2e/README.md` | Human documentation for E2E scope and usage |
| `test/e2e/__init__.py` | Package marker |
| `test/OWNERS` | Reviewers: `acsoto`, `LiZhenCheng9527`, `MahaoAlex`, `tjucoder`, `YaoZengzeng`; approvers: `MahaoAlex`, `YaoZengzeng` |

### 6.2 E2E framework (from `run_e2e.sh`)

- **Cluster:** Kind, name default `agentcube-e2e`; optional delete/recreate via `E2E_CLEAN_CLUSTER` (default `true`).
- **External deps:** Docker pulls `registry.k8s.io/agent-sandbox/agent-sandbox-controller:${AGENT_SANDBOX_VERSION}` (default **`v0.1.1` in script**) and `python:3.9-slim`; kubectl applies agent-sandbox `manifest.yaml` and `extensions.yaml` from GitHub releases.
- **Images built:** `make docker-build`, `docker-build-router`, `docker-build-picod`; loaded into kind; Helm uses local image names `workloadmanager` / `agentcube-router` with tag `latest`.
- **Redis:** In-cluster Deployment + Service on port 6379 in `AGENTCUBE_NAMESPACE` (default `agentcube`).
- **Helm:** `helm upgrade --install agentcube manifests/charts/base` with `--set-json` for `workloadmanager.extraEnv` and `router.extraEnv`, `router.rbac.create=true`, `router.serviceAccountName=agentcube-router`, redis addr/password.
- **Auth for tests:** SA `e2e-test` + `ClusterRoleBinding` to existing **`ClusterRole` `workloadmanager`**; token via `kubectl create token`.
- **Test execution:** `go test -v ./test/e2e/...` with `WORKLOAD_MANAGER_URL`, `ROUTER_URL`, `API_TOKEN`; then `test_codeinterpreter.py` with same env + `AGENTCUBE_NAMESPACE`.

---

## 7. Documentation (`docs/`)

### 7.1 Top-level `docs/` (Markdown outside Docusaurus)

- **Getting started / guides:** `getting-started.md`
- **Developer guides:** `devguide/code-interpreter-using-langchain.md`, `devguide/code-interpreter-python-sdk.md`
- **Design / proposals:** `design/` — runtime template, PicoD, router, agentcube proposals, authentication, CLI design, SVG assets, etc.

### 7.2 Docusaurus site (`docs/agentcube/`)

| Aspect | Detail |
|--------|--------|
| **System** | Docusaurus **3.9.2** (`@docusaurus/core`, preset-classic, `@docusaurus/theme-mermaid`) |
| **`package.json`** | `name`: `agentcube`, `version`: `0.0.0`, `private`: true, `engines.node`: `>=20.0` |
| **Scripts** | `start`, `build`, `serve`, `deploy`, `clear`, `swizzle`, `write-translations`, `write-heading-ids`, `typecheck` (tsc) |
| **Config** | `docusaurus.config.ts`: title `AgentCube`, tagline `Native AI Agent Workload Management for Kubernetes`, `organizationName` `volcano-sh`, `projectName` `agentcube`, Mermaid enabled, classic preset with docs sidebar `sidebars.ts`, blog with RSS/atom |
| **Content** | `docs/agentcube/docs/`: `intro.md`, `getting-started.md`, `architecture/` (overview, components, security), `developer-guide/` (intro, building-runtimes, testing, local-development, project-structure), `tutorials/` (first-agent, python-sdk, pcap-analyzer, category JSON) |
| **Other** | `src/pages/` (home, markdown page), `src/components/HomepageFeatures/`, `blog/` (`authors.yml`, `tags.yml`), static assets under `static/img/` |
| **README** | `docs/agentcube/README.md` describes local dev for the site |

### 7.3 `docs/OWNERS`

Reviewers/approvers listed for docs area.

---

## 8. Root files

| File | Role |
|------|------|
| `LICENSE` | Apache License 2.0 (standard text). |
| `OWNERS` | Repo reviewers/approvers (`hzxuzhonghu`, `tjucoder`, `VanderChen`, `YaoZengzeng` / `hzxuzhonghu`, `kevin-wangzefeng`). |
| `CODE_OF_CONDUCT.md` | Points to Volcano community code of conduct URL. |
| `README.md` | Project overview (proposal phase, goals, Volcano context). |
| `pyproject.toml` | Monorepo-oriented setuptools config: project `agentcube` 0.1.0, Python `>=3.10`, packages from `sdk-python` and `.` including `agentcube*` and `test*`; **Ruff** config (`line-length` 120, `py310`, rules E/F/W). |
| `pyrightconfig.json` | Typecheck `sdk-python` and `test/e2e`; excludes large dirs (`client-go`, `cmd`, `pkg`, `docs`, `manifests`, etc.); `pythonVersion` `3.8`, `typeCheckingMode` `basic`. |
| `package.json` | **Empty object:** `{}` (placeholder only at repo root). |

---

## Appendix: reproducibility notes

1. **Helm + CRDs:** Installing the chart from `manifests/charts/base` applies CRDs from `crds/` first, then templates; set `redis.addr` and `redis.password` at install (defaults are empty strings).
2. **Router RBAC:** Default chart leaves `router.rbac.create: false`; E2E explicitly sets `true` and `serviceAccountName` to match.
3. **Version skew:** CI E2E uses Go **1.23**; Docker builders use Go **1.24.9** (WM/router) and **1.24.4** (picod, release workflow). Picod Dockerfile uses `COPY . .` (full repo context).
4. **Makefile vs E2E:** `AGENT_SANDBOX_VERSION` defaults differ between `Makefile` (`main`) and `run_e2e.sh` (`v0.1.1`).

This specification is a faithful structural export of `/tmp/agentcube-ref` as read for this document; behavior of runtime binaries is out of scope.
