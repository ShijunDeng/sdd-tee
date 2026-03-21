# Deployment Design

Source tree: `/tmp/agentcube-ref` (reference clone). Paths below are relative to repository root unless noted.

## Chart.yaml

| Field | Value |
|--------|--------|
| `apiVersion` | `v1` |
| `name` | `agentcube` |
| `description` | `A Helm chart for AgentCube` |
| `version` | `0.1.0` |
| `appVersion` | `1.0.0` |

## values.yaml — full key tree (type & default)

| Path | Type | Default |
|------|------|---------|
| `imagePullSecrets` | array | `[]` |
| `nameOverride` | string | `""` |
| `fullnameOverride` | string | `""` |
| `redis.addr` | string | `""` |
| `redis.password` | string | `""` |
| `router.replicas` | int | `1` |
| `router.image.repository` | string | `ghcr.io/volcano-sh/agentcube-router` |
| `router.image.pullPolicy` | string | `IfNotPresent` |
| `router.image.tag` | string | `latest` |
| `router.service.type` | string | `ClusterIP` |
| `router.service.port` | int | `8080` |
| `router.service.targetPort` | int | `8080` |
| `router.resources.limits.cpu` | string | `500m` |
| `router.resources.limits.memory` | string | `512Mi` |
| `router.resources.requests.cpu` | string | `100m` |
| `router.resources.requests.memory` | string | `128Mi` |
| `router.config` | object | `{}` |
| `router.extraEnv` | array | `[]` |
| `router.serviceAccountName` | string | `""` |
| `router.rbac.create` | bool | `false` |
| `workloadmanager.replicas` | int | `1` |
| `workloadmanager.image.repository` | string | `ghcr.io/volcano-sh/workloadmanager` |
| `workloadmanager.image.pullPolicy` | string | `IfNotPresent` |
| `workloadmanager.image.tag` | string | `latest` |
| `workloadmanager.service.type` | string | `ClusterIP` |
| `workloadmanager.service.port` | int | `8080` |
| `workloadmanager.resources.limits.cpu` | string | `500m` |
| `workloadmanager.resources.limits.memory` | string | `512Mi` |
| `workloadmanager.resources.requests.cpu` | string | `100m` |
| `workloadmanager.resources.requests.memory` | string | `128Mi` |
| `workloadmanager.extraEnv` | array | `[]` |
| `volcano.scheduler.enabled` | bool | `false` |
| `volcano.scheduler.replicas` | int | `1` |
| `volcano.scheduler.image.repository` | string | `ghcr.io/volcano-sh/vc-agent-scheduler` |
| `volcano.scheduler.image.pullPolicy` | string | `IfNotPresent` |
| `volcano.scheduler.image.tag` | string | `latest` |

Comments in `values.yaml` state Redis settings “must be provided by the user during installation”; defaults are still empty strings.

## Template files (`manifests/charts/base/templates/`)

### `workloadmanager.yaml`

| Kind | Name | Namespace | Notes |
|------|------|-----------|--------|
| `Deployment` | `workloadmanager` | `{{ .Release.Namespace }}` | `replicas`: `workloadmanager.replicas`; `serviceAccountName`: `workloadmanager`; optional `imagePullSecrets`; container `workloadmanager`; image `repository:tag`; `imagePullPolicy`; port `http` → `workloadmanager.service.port`; **env**: `AGENTCUBE_NAMESPACE` (fieldRef `metadata.namespace`), `REDIS_PASSWORD`, `REDIS_ADDR`, plus `workloadmanager.extraEnv`; **args**: `--port={{ workloadmanager.service.port }}`, `--runtime-class-name=` (empty); **resources**: from values; **liveness/readiness**: HTTP GET `/health` on service port, delays 10s/10s and 5s/5s |
| `Service` | `workloadmanager` | release ns | `type`: `workloadmanager.service.type`; port & `targetPort`: `workloadmanager.service.port`; selector `app: workloadmanager` |

### `agentcube-router.yaml`

| Kind | Name | Notes |
|------|------|--------|
| `Deployment` | `agentcube-router` | `replicas`: `router.replicas`; **conditional** `serviceAccountName` if `router.serviceAccountName` non-empty; optional `imagePullSecrets`; container `agentcube-router`; image from `router.image`; container port `router.service.targetPort`; **env**: `AGENTCUBE_NAMESPACE` (fieldRef), `REDIS_ADDR`, `REDIS_PASSWORD`, `WORKLOAD_MANAGER_URL` = `http://workloadmanager.{{ .Release.Namespace }}.svc.cluster.local:{{ workloadmanager.service.port }}`, plus `router.extraEnv`; **args**: `--port={{ router.service.targetPort }}`, `--debug`; **resources** from values; **liveness** `/health/live`, **readiness** `/health/ready` on targetPort, 1s initial, 2s period |
| `Service` | `agentcube-router` | `type` `router.service.type`; `port` `router.service.port`, `targetPort` `router.service.targetPort`; selector `app: agentcube-router` |

### `rbac/workloadmanager.yaml`

| Kind | Name | Scope | Notes |
|------|------|-------|--------|
| `ServiceAccount` | `workloadmanager` | release namespace | — |
| `ClusterRole` | `workloadmanager` | cluster | rules below |
| `ClusterRoleBinding` | `workloadmanager` | cluster | binds `ClusterRole/workloadmanager` to `ServiceAccount/workloadmanager` in release namespace |

### `rbac-router.yaml`

Rendered **only if** `router.rbac.create` is true.

| Kind | Name pattern | Notes |
|------|--------------|--------|
| `ServiceAccount` | `{{ router.serviceAccountName \| default "agentcube-router" }}` | release namespace |
| `Role` | same as SA name | rules: `secrets` in `""` apiGroup, full verb set `get,list,watch,create,update,patch,delete` |
| `RoleBinding` | same | subject: SA above; `Role` ref same name |

### `volcano-agent-scheduler-development.yaml`

Rendered **only if** `volcano.scheduler.enabled`.

Creates (in order in file): `ServiceAccount/volcano-agent-scheduler`; `ConfigMap/volcano-agent-scheduler-configmap` with key `agent-scheduler.conf` (actions `allocate`, tiers predicates/nodeorder); `ClusterRole/volcano-agent-scheduler` (large rule set — see RBAC section); `ClusterRoleBinding/volcano-agent-scheduler-role`; `Service/volcano-agent-scheduler-service` (port 8080 metrics annotations); `Deployment/volcano-agent-scheduler` with `replicas` from `volcano.scheduler.replicas`, image from values, args including `--scheduler-name=agent-scheduler`, security contexts, volumes for config + emptyDir.

## RBAC rules (exact apiGroups / resources / verbs)

### ClusterRole `workloadmanager`

| apiGroups | resources | verbs |
|-----------|-----------|-------|
| `agents.x-k8s.io` | `sandboxes` | `get,list,watch,create,update,patch,delete` |
| `extensions.agents.x-k8s.io` | `sandboxclaims` | `get,list,watch,create,update,patch,delete` |
| `extensions.agents.x-k8s.io` | `sandboxtemplates` | `get,list,watch,create,update,patch,delete` |
| `extensions.agents.x-k8s.io` | `sandboxwarmpools` | `get,list,watch,create,update,patch,delete` |
| `extensions.agents.x-k8s.io` | `sandboxwarmpools/status` | `get,update,patch` |
| `runtime.agentcube.volcano.sh` | `codeinterpreters` | `get,list,watch,create,update,patch,delete` |
| `runtime.agentcube.volcano.sh` | `codeinterpreters/status` | `get,update,patch` |
| `runtime.agentcube.volcano.sh` | `codeinterpreters/finalizers` | `update` |
| `runtime.agentcube.volcano.sh` | `agentruntimes` | `get,list,watch` |
| `runtime.agentcube.volcano.sh` | `agentruntimes/status` | `update,patch` |
| `""` | `pods` | `get,list,watch` |
| `authentication.k8s.io` | `tokenreviews` | `create` |
| `""` | `secrets` | `get,list,watch,create,update,patch,delete` |

### Role `router` (optional)

| apiGroups | resources | verbs |
|-----------|-----------|-------|
| `""` | `secrets` | `get,list,watch,create,update,patch,delete` |

### ClusterRole `volcano-agent-scheduler` (when enabled)

| apiGroups | resources | verbs |
|-----------|-----------|-------|
| `apiextensions.k8s.io` | `customresourcedefinitions` | `create,get,list,watch,delete` |
| `""` | `events` | `create,list,watch,update,patch` |
| `""` | `pods` | `get,list,watch,patch,delete` |
| `""` | `pods/status` | `update` |
| `""` | `pods/binding` | `create` |
| `""` | `persistentvolumeclaims` | `list,watch,update` |
| `""` | `persistentvolumes` | `list,watch,update` |
| `""` | `namespaces,services,replicationcontrollers` | `list,watch,get` |
| `""` | `resourcequotas` | `list,watch` |
| `""` | `nodes` | `get,list,watch,update,patch` |
| `storage.k8s.io` | `storageclasses,csinodes,csidrivers,csistoragecapacities,volumeattachments` | `list,watch` |
| `policy` | `poddisruptionbudgets` | `list,watch` |
| `scheduling.k8s.io` | `priorityclasses` | `get,list,watch` |
| `scheduling.incubator.k8s.io`, `scheduling.volcano.sh` | `podgroups` | `list,watch,update` |
| `""` | `configmaps` | `get,list,watch,create,delete,update` |
| `apps` | `daemonsets,replicasets,statefulsets` | `list,watch,get` |
| `coordination.k8s.io` | `leases` | `get,create,update,watch` |
| `resource.k8s.io` | `resourceclaims` | `get,list,watch,create,update,patch` |
| `resource.k8s.io` | `resourceclaims/status` | `update` |
| `resource.k8s.io` | `deviceclasses,resourceslices` | `get,list,watch,create` |
| `shard.volcano.sh` | `nodeshards` | `list,watch,get,update` |

## CRD definitions shipped (`manifests/charts/base/crds/`)

| File | CRD `metadata.name` | group | versions | scope | Notes |
|------|---------------------|-------|----------|-------|--------|
| `runtime.agentcube.volcano.sh_agentruntimes.yaml` | `agentruntimes.runtime.agentcube.volcano.sh` | `runtime.agentcube.volcano.sh` | `v1alpha1` (served+storage); printer column Age | `Namespaced` | `openAPIV3Schema` includes root fields `apiVersion`, `kind`, `metadata`, `spec`, `status`. **spec.required**: `maxSessionDuration`, `podTemplate`, `sessionTimeout`, `targetPort`. **Key spec fields**: `maxSessionDuration` (string, default `8h`); `sessionTimeout` (string, default `15m`); `targetPort` (array of port objects: required `port`, `protocol` enum HTTP/HTTPS, optional `name`, `pathPrefix`); `podTemplate` (annotations, labels, nested `spec` = full PodSpec-shaped schema). **status**: conditions, etc. Annotation `controller-gen.kubebuilder.io/version: v0.17.2` |
| `runtime.agentcube.volcano.sh_codeinterpreters.yaml` | `codeinterpreters.runtime.agentcube.volcano.sh` | `runtime.agentcube.volcano.sh` | `v1alpha1` | `Namespaced` | **spec** includes `authMode` enum `picod|none` default `picod`; `maxSessionDuration` default `8h`; `sessionTimeout` default `15m`; `ports` (same TargetPort shape as above); `template` (image, command, args, env, resources, runtimeClassName, etc.); optional `warmPoolSize` int32. **spec.required**: `template`. **status**: `conditions`, `ready`; subresource `status`. Same controller-gen version annotation |

## Dockerfiles

### `docker/Dockerfile` (workloadmanager)

| Stage | Base | Purpose |
|-------|------|---------|
| builder | `golang:1.24.9-alpine` | `WORKDIR /workspace`; copy `go.mod`/`go.sum`; `go mod download`; copy `cmd/`, `pkg/`; build `CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -ldflags="-s -w" -o workloadmanager ./cmd/workload-manager` with BuildKit cache mounts |
| runtime | `alpine:3.19` | `apk add ca-certificates`; `WORKDIR /app`; copy binary; `adduser -D -u 1000 apiserver`; `USER apiserver`; `EXPOSE 8080`; `ENTRYPOINT ["/app/workloadmanager"]`; `CMD ["--port=8080"]` |

Build args: `TARGETOS=linux`, `TARGETARCH` (implicit platform).

### `docker/Dockerfile.router`

Same pattern as workloadmanager builder, plus `COPY client-go/ client-go/`; output binary `agentcube-router` from `./cmd/router`; runtime user `router` UID 1000; `CMD ["--port=8080", "--debug"]`.

### `docker/Dockerfile.picod`

| Stage | Base | Purpose |
|-------|------|---------|
| builder | `golang:1.24.4` | `WORKDIR /app`; copy mod files; download; `COPY . .`; build `picod` from `./cmd/picod` with `CGO_ENABLED=0` |
| runtime | `ubuntu:24.04` | `apt-get install -y python3`; `WORKDIR /root/`; copy binary; **runs as root** (comment: chattr on pubkey + sandbox permissions); `ENTRYPOINT ["./picod"]` |

## Makefile — variables (key)

| Variable | Default / definition |
|----------|----------------------|
| `HUB` | `ghcr.io/volcano-sh` |
| `TAG` | `latest` |
| `PROJECT_DIR` | directory of Makefile |
| `GOBIN` | from `go env` |
| `CONTAINER_TOOL` | `docker` |
| `SHELL` | `/usr/bin/env bash -o pipefail` |
| `LOCALBIN` | `$(shell pwd)/bin` |
| `CONTROLLER_GEN` | `$(LOCALBIN)/controller-gen` |
| `GOLANGCI_LINT` | `$(LOCALBIN)/golangci-lint` |
| `CONTROLLER_TOOLS_VERSION` | `v0.17.2` |
| `GOLANGCI_LINT_VERSION` | `v1.64.1` |
| `WORKLOAD_MANAGER_IMAGE` | `workloadmanager:latest` |
| `ROUTER_IMAGE` | `agentcube-router:latest` |
| `PICOD_IMAGE` | `picod:latest` |
| `IMAGE_REGISTRY` | `""` |
| `E2E_CLUSTER_NAME` | `agentcube-e2e` |
| `AGENT_SANDBOX_REPO` | `https://github.com/kubernetes-sigs/agent-sandbox.git` |
| `AGENT_SANDBOX_VERSION` | `main` (Makefile comment; E2E script overrides — see CI design) |

## Makefile — targets

| Target | Depends / notes |
|--------|-----------------|
| `all` | → `build` |
| `help` | awk help from `##` comments |
| `gen-crd` | `controller-gen`; `crd paths=./pkg/apis/runtime/v1alpha1/...` → `manifests/charts/base/crds` |
| `generate` | `controller-gen object` + `gen-crd` + `go mod tidy` |
| `gen-client` | `bash hack/update-codegen.sh`; `go mod tidy` |
| `gen-all` | `generate` + `gen-client` |
| `gen-check` | `gen-all` then `git diff --exit-code` |
| `build` | `generate`; `go build -o bin/workloadmanager ./cmd/workload-manager` |
| `build-agentd` | `generate`; `go build -o bin/agentd ./cmd/agentd` |
| `build-router` | `generate`; `go build -o bin/agentcube-router ./cmd/router` |
| `build-all` | `build` + `build-agentd` + `build-router` |
| `run` | `go run ./cmd/workload-manager/main.go --port=8080 --ssh-username=sandbox --ssh-port=22` |
| `run-local` | same with `--kubeconfig=${HOME}/.kube/config` |
| `run-router` | `go run ./cmd/router/main.go --port=8080 --debug` |
| `clean` | `rm -rf bin/` and root binaries |
| `deps` | `go mod download`; `go mod tidy` |
| `update-deps` | `go get -u ./...`; `go mod tidy` |
| `test` | `go test -v ./...` |
| `fmt` | `go fmt ./...` |
| `vet` | `go vet ./...` |
| `lint` | `$(GOLANGCI_LINT) run ./...` |
| `gen-copyright` | `hack/update-copyright.sh` |
| `install` | `build` + `sudo cp bin/workloadmanager /usr/local/bin/` |
| `docker-build` | `docker build -f docker/Dockerfile -t $(WORKLOAD_MANAGER_IMAGE) .` |
| `docker-buildx` | buildx linux/amd64,arm64 |
| `docker-buildx-push` | requires `IMAGE_REGISTRY`; buildx `--push` |
| `docker-push` | tag+push workloadmanager |
| `kind-load` | `kind load docker-image $(WORKLOAD_MANAGER_IMAGE)` |
| `docker-build-router` / `docker-buildx-router` / `docker-buildx-push-router` / `docker-push-router` / `kind-load-router` | same pattern for router image |
| `docker-build-picod` / `docker-buildx-picod` / `docker-buildx-push-picod` / `docker-push-picod` | same for picod |
| `controller-gen` / `golangci-lint` | download via `go-install-tool` macro |
| `e2e` | `./test/e2e/run_e2e.sh` |
| `e2e-clean` | `kind delete cluster --name $(E2E_CLUSTER_NAME)`; `rm -rf /tmp/agent-sandbox` |
| `build-python-sdk` | copy `LICENSE` to `sdk-python`, `python3 -m build` in `sdk-python`, remove copied LICENSE |

## hack/ scripts

| File | Purpose |
|------|---------|
| `hack/update-codegen.sh` | Runs `k8s.io/code-generator` **v0.34.1**: sources `kube_codegen.sh`, calls `kube::codegen::gen_client --with-watch --output-dir client-go --output-pkg github.com/volcano-sh/agentcube/client-go --boilerplate hack/boilerplate.go.txt --one-input-api runtime/v1alpha1` on `pkg/apis`; post-processes lister files with `sed` to append `.GroupResource()` for codeinterpreter/agentruntime resources |
| `hack/update-copyright.sh` | Prepends Apache/Volcano boilerplate to `*.go` and `*.py` under git root (excluding vendor/venv) if missing “Copyright The Volcano Authors”; uses `hack/boilerplate.go.txt` / `hack/boilerplate.py.txt`; requires `sponge` (moreutils) |
| `hack/boilerplate.go.txt` | Go file header template |
| `hack/boilerplate.py.txt` | Python file header template |

## Helm / E2E reference command (from `test/e2e/run_e2e.sh`)

Illustrative install used in E2E:

```bash
helm upgrade --install agentcube manifests/charts/base \
  --namespace "${AGENTCUBE_NAMESPACE}" \
  --create-namespace \
  --set redis.addr="redis.${AGENTCUBE_NAMESPACE}.svc.cluster.local:6379" \
  --set redis.password="" \
  --set workloadmanager.image.repository="workloadmanager" \
  --set workloadmanager.image.tag="latest" \
  --set-json 'workloadmanager.extraEnv=[{"name":"REDIS_PASSWORD_REQUIRED","value":"false"},{"name":"JWT_KEY_SECRET_NAMESPACE","value":"agentcube"}]' \
  --set router.image.repository="agentcube-router" \
  --set router.image.tag="latest" \
  --set router.rbac.create=true \
  --set router.serviceAccountName="agentcube-router" \
  --set-json 'router.extraEnv=[{"name":"REDIS_PASSWORD_REQUIRED","value":"false"}]' \
  --wait
```

Images are expected to be loaded into Kind with local names `workloadmanager:latest`, `agentcube-router:latest`, `picod:latest` after `make docker-build` variants.
