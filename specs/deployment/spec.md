# Deployment Specification

## Purpose
Deploy AgentCube control-plane components (Workload Manager, Router), optional Volcano agent scheduler, and required Redis connectivity via the `agentcube` Helm chart, container images, and Makefile-driven builds.

## Requirements

### Requirement: Helm chart installation
The system SHALL support installing/upgrading the AgentCube stack with Helm from `manifests/charts/base`, including namespace creation and values for Redis, images, replicas, and optional router RBAC.

#### Scenario: Install with release namespace
- **GIVEN** a Kubernetes cluster and Helm 3 available
- **WHEN** the operator runs `helm upgrade --install <release> manifests/charts/base --namespace <ns> --create-namespace` with required `redis.addr` (and optional `redis.password`) plus component image overrides as needed
- **THEN** chart templates apply Workload Manager and Router workloads (and optional Volcano resources when enabled) in `<ns>` without manual editing of rendered YAML

### Requirement: Helm values and Redis connectivity
The system SHALL require Redis address configuration for Workload Manager and Router at runtime via chart values `redis.addr` and `redis.password` (empty password permitted when Redis has no auth).

#### Scenario: Components receive Redis env vars
- **GIVEN** `redis.addr` and `redis.password` set in Helm values
- **WHEN** pods for `workloadmanager` and `agentcube-router` start
- **THEN** each container SHALL have environment variables `REDIS_ADDR` and `REDIS_PASSWORD` populated from those values

### Requirement: Workload Manager deployment shape
The system SHALL deploy Workload Manager as a `Deployment` and `Service` named `workloadmanager` with replica count, container image, service type/port, resource requests/limits, health probes, and optional `extraEnv` driven from `values.yaml`.

#### Scenario: Default replica and service exposure
- **GIVEN** default chart values
- **WHEN** the chart is installed
- **THEN** the Workload Manager `Deployment` SHALL use `workloadmanager.replicas` (default 1), expose HTTP on `workloadmanager.service.port` (default 8080), and use liveness/readiness HTTP GET `/health` on that port

### Requirement: Router deployment shape
The system SHALL deploy the Router as a `Deployment` and `Service` named `agentcube-router` with replica count, image, `ClusterIP` service mapping `port`→`targetPort`, resource requests/limits, optional dedicated `serviceAccountName`, and `WORKLOAD_MANAGER_URL` pointing at the in-cluster Workload Manager service.

#### Scenario: Router reaches Workload Manager by DNS
- **GIVEN** release namespace `N` and Workload Manager service port `P` from values
- **WHEN** the Router pod starts
- **THEN** it SHALL have `WORKLOAD_MANAGER_URL` set to `http://workloadmanager.N.svc.cluster.local:P` and container args including `--port=<targetPort>` and `--debug`

### Requirement: Workload Manager ClusterRole permissions
The system SHALL create a `ServiceAccount` `workloadmanager`, a `ClusterRole` `workloadmanager`, and `ClusterRoleBinding` `workloadmanager` granting the rules required for agent-sandbox, AgentCube runtime CRDs, core workloads, auth, and secrets.

#### Scenario: Binding ties SA to cluster role
- **GIVEN** chart installation in namespace `N`
- **WHEN** RBAC resources are applied
- **THEN** subject `ServiceAccount/workloadmanager` in namespace `N` SHALL be bound to `ClusterRole/workloadmanager` via `ClusterRoleBinding/workloadmanager`

### Requirement: Optional Router namespace Role
The system SHALL optionally create namespace-scoped `ServiceAccount`, `Role`, and `RoleBinding` for the Router when `router.rbac.create` is true, granting secret management in that namespace.

#### Scenario: RBAC off by default
- **GIVEN** `router.rbac.create: false`
- **WHEN** the chart renders templates
- **THEN** Router optional RBAC manifests SHALL NOT be emitted

#### Scenario: RBAC on with named service account
- **GIVEN** `router.rbac.create: true` and `router.serviceAccountName` set (or defaulted by template to `agentcube-router`)
- **WHEN** the chart is applied
- **THEN** Router pods MAY use that `serviceAccountName` and the Role SHALL allow verbs on `secrets` in the release namespace

### Requirement: Optional Volcano agent scheduler
The system SHALL optionally deploy Volcano agent scheduler resources (ServiceAccount, ConfigMap, ClusterRole, ClusterRoleBinding, Service, Deployment) when `volcano.scheduler.enabled` is true.

#### Scenario: Scheduler disabled
- **GIVEN** `volcano.scheduler.enabled: false` (default)
- **WHEN** templates render
- **THEN** no Volcano scheduler objects SHALL be created

### Requirement: CRDs shipped with the chart
The system SHALL ship `CustomResourceDefinition` manifests for `agentruntimes` and `codeinterpreters` under the chart `crds/` directory so Helm installs them with the chart lifecycle.

#### Scenario: CRD group and scope
- **GIVEN** chart path `manifests/charts/base`
- **WHEN** CRD YAML is applied
- **THEN** both CRDs SHALL use API group `runtime.agentcube.volcano.sh`, version `v1alpha1`, and `scope: Namespaced`

### Requirement: Docker images for core binaries
The system SHALL provide Dockerfiles to build three images: Workload Manager (`docker/Dockerfile`), Router (`docker/Dockerfile.router`), and picod (`docker/Dockerfile.picod`).

#### Scenario: Multi-stage Go build for control plane
- **GIVEN** repository root as build context
- **WHEN** `docker build -f docker/Dockerfile` (or `Dockerfile.router`) runs
- **THEN** the image SHALL compile the respective Go binary with `CGO_ENABLED=0` and run it from Alpine 3.19 as a non-root user (`apiserver` UID 1000 or `router` UID 1000) exposing port 8080

### Requirement: Makefile build targets
The system SHALL expose Make targets to build binaries (`build`, related targets), run tests (`test`), build/push Docker images (`docker-*`), run code generation (`generate`, `gen-crd`, `gen-client`, `gen-all`, `gen-check`), and run E2E (`e2e`, `e2e-clean`).

#### Scenario: Default `make` builds workload manager
- **GIVEN** Go toolchain and generated code prerequisites
- **WHEN** the operator runs `make` (default `all` → `build`)
- **THEN** `bin/workloadmanager` SHALL be produced from `./cmd/workload-manager` after `generate`

#### Scenario: E2E entrypoint
- **GIVEN** Kind, kubectl, Docker, Helm, and curl available
- **WHEN** the operator runs `make e2e`
- **THEN** the repository SHALL execute `./test/e2e/run_e2e.sh` which provisions the cluster (unless skipped), deploys dependencies, and runs Go and Python E2E tests
