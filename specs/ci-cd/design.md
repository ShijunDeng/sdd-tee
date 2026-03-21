# AgentCube CI/CD — Design

Sources: `/tmp/agentcube-ref/.github/workflows/`, `/tmp/agentcube-ref/test/`, and (for Make targets) `/tmp/agentcube-ref/Makefile`.

## GitHub Actions workflows (summary table)

| Filename | Workflow `name` | Trigger events | Path filters (dorny/paths-filter or notes) | Jobs | Key steps | Env vars (job/step) | Secrets |
|----------|-----------------|----------------|---------------------------------------------|------|-----------|---------------------|---------|
| `main.yml` | Agentcube CI Workflow | `pull_request` → `main`, `release-*` | *(none)* | `build` | Checkout; Docker Buildx setup; verify Docker; `make docker-build` | — | — |
| `e2e.yml` | Agentcube E2E Tests | `pull_request` → `main`, `release-*` | *(none)* | `e2e-test` | Checkout; Go 1.23; `helm/kind-action@v1` **install_only** Kind v0.30.0, `cluster_name: agentcube-e2e`; `export ARTIFACTS_PATH=${{ github.workspace }}/e2e-logs`; `make e2e`; on failure upload `e2e-logs/`; `always` → `make e2e-clean` | `ARTIFACTS_PATH` (shell) | — |
| `lint.yml` | Lint | `pull_request` → `main`, `release-*` | `lint`: `**/*.go`, `go.mod`, `go.sum`, `.golangci.yml`, `.github/workflows/lint.yml` | `golangci` | Checkout; paths-filter; if changed: Go 1.24; `make lint` | — | — |
| `python-sdk-tests.yml` | Python SDK Tests | `pull_request`, `merge_group` | `sdk`: `sdk-python/**` | `python-sdk-tests` | Checkout; paths-filter; if changed: Python 3.12 in `sdk-python/`; `pip install pytest`; `pip install -e .`; `python -m pytest tests/ -v` | Default `working-directory: sdk-python` | — |
| `python-lint.yml` | Python Lint | `pull_request` → `main`, `release-*` | `python`: `cmd/cli/**`, `sdk-python/**`, `example/**`, `test/**/*.py`, `pyproject.toml`, workflow self | `python_lint` | Checkout; paths-filter; if changed: Python 3.10; `pip install ruff`; `ruff check . --config pyproject.toml` | — | — |
| `test-coverage.yml` | Test Coverage | `pull_request`, `merge_group`, `workflow_call` | `coverage`: `**` minus `*.md`, `*.svg`, `*.png` | `coverage` | Checkout; paths-filter; if changed: free disk space; Go 1.24; `go test` with coverage; step summary; Codecov upload; artifact `go-coverage` | `CODECOV_TOKEN` passed to Codecov action when present | `secrets.CODECOV_TOKEN` (optional; declared for `workflow_call`) |
| `codegen-check.yml` | Codegen Check | `pull_request` → `main`, `release-*` | `codegen`: `pkg/apis/**`, `hack/**`, `.github/workflows/**`, `Makefile` | `codegen-check` | Checkout; paths-filter; if changed: Go 1.24.4; `make gen-check` | — | — |
| `copyright-check.yml` | Copyright Check | `pull_request` → `main`, `release-*` | `copyright`: all files except `*.md`, `*.svg`, `*.png`, `docs/**`, `.github/**` | `build` | Checkout; paths-filter; if changed: `apt install moreutils`; `make gen-copyright`; `git diff --exit-code` | — | — |
| `codespell.yml` | Codespell | `pull_request` → `main`, `release-*` | *(none — scans tree after temporarily removing some manifests)* | `codespell` | Backup/remove `pyproject.toml`, `package.json`, `package-lock.json`; `pip install codespell`; `codespell` with `--check-filenames`, `--skip`, `--ignore-words-list`; restore files | — | — |
| `build-push-release.yml` | Build and Push Release Images | `push` → `main`; `push` tags `v*.*.*`, `v*.*.*-*` | *(none)* | `build-and-push` | Checkout; Go 1.24.4; Buildx; `docker/login-action` to `ghcr.io`; set `TAG` from ref; `make docker-buildx-push` (workload manager), `docker-buildx-push-router`, `docker-buildx-push-picod` with `IMAGE_REGISTRY` | `TAG`, `IMAGE_REGISTRY=ghcr.io/${{ github.repository_owner }}` | `GITHUB_TOKEN` (registry login) |
| `dify-plugin-publish.yml` | Dify Plugin Publish | `push` tags `dify-plugin/v*` | *(none)* | `publish` | Download `dify-plugin` CLI 0.0.6; install `yq`; read `manifest.yaml`; package plugin; checkout `author/dify-plugins` with token; move `.difypkg`; branch, commit, push; `gh pr create` to `langgenius/dify-plugins` | `GH_TOKEN` on PR step | `PLUGIN_ACTION` (repo checkout + `gh`; cross-repo PR) |
| `workflows-approve.yml` | Approve Workflows | `pull_request_target` types `labeled`, `synchronize` → `main`, `release-**` | *(logic: first-time contributor vs `ok-to-test` label)* | `approve` | `github-script`: list contributor PRs; if not first-time or has `ok-to-test`, list `action_required` workflow runs for SHA and approve | — | `GITHUB_TOKEN` |

### Workflow notes

- **`e2e.yml`**: Uses Kind action with `install_only: true` so the cluster is created by `run_e2e.sh` (`kind create cluster`), avoiding double-creation.
- **`test-coverage.yml`**: `workflow_call` declares `CODECOV_TOKEN` optional for reusable invocation; PR runs use the repo secret when configured.
- **`build-push-release.yml`**: Uses older action major versions (`checkout@v3`, `setup-go@v4`, `buildx@v2`) than most other workflows.

---

## E2E test setup (`test/e2e/run_e2e.sh`)

### Kind cluster

| Item | Value / behavior |
|------|------------------|
| Default cluster name | `E2E_CLUSTER_NAME` → `agentcube-e2e` |
| Creation | `kind create cluster --name "${E2E_CLUSTER_NAME}"` if missing; if exists and `E2E_CLEAN_CLUSTER=true` (default), delete then recreate |
| CI alignment | `.github/workflows/e2e.yml` installs Kind **v0.30.0** via `helm/kind-action@v1` (`install_only: true`) |
| Skip setup | `E2E_SKIP_SETUP=true` skips `run_setup` and assumes an existing cluster |

### CRD / agent-sandbox installation

Applied via `kubectl apply --validate=false` after downloading release assets (URLs built from `AGENT_SANDBOX_VERSION`, default **`v0.1.1`**):

1. `https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${AGENT_SANDBOX_VERSION}/manifest.yaml`
2. `https://github.com/kubernetes-sigs/agent-sandbox/releases/download/${AGENT_SANDBOX_VERSION}/extensions.yaml`

### Images pre-pulled and loaded into Kind

- `registry.k8s.io/agent-sandbox/agent-sandbox-controller:${AGENT_SANDBOX_VERSION}`
- `python:3.9-slim` (echo agent workload)

Local images built and loaded:

- `make docker-build` → default `WORKLOAD_MANAGER_IMAGE` **`workloadmanager:latest`**
- `make docker-build-router` → **`agentcube-router:latest`**
- `make docker-build-picod` → **`picod:latest`**
- `REDIS_IMAGE` default **`redis:7-alpine`** (Deployment + Service in namespace)

### Helm (AgentCube chart)

| Item | Value |
|------|--------|
| Chart path | `manifests/charts/base` |
| Release / namespace | `agentcube` in `AGENTCUBE_NAMESPACE` (default `agentcube`), `--create-namespace` |
| Redis addr | `redis.${AGENTCUBE_NAMESPACE}.svc.cluster.local:6379`, password empty |
| Workload manager image | `repository=workloadmanager`, `tag=latest` |
| Router image | `repository=agentcube-router`, `tag=latest` |
| Router RBAC | `router.rbac.create=true`, `router.serviceAccountName=agentcube-router` |
| Extra env (JSON via `--set-json`) | Workload manager: `REDIS_PASSWORD_REQUIRED=false`, `JWT_KEY_SECRET_NAMESPACE=agentcube`; Router: `REDIS_PASSWORD_REQUIRED=false` |
| Wait | `helm upgrade --install ... --wait` |

### Kubernetes fixtures applied during setup

| Path | Purpose |
|------|---------|
| `test/e2e/echo_agent.yaml` | `AgentRuntime` `echo-agent` in `agentcube` |
| Generated from `echo_agent.yaml` (sed) | `echo-agent-short-ttl` with `sessionTimeout: "30s"` for TTL tests |
| `test/e2e/e2e_code_interpreter.yaml` | `CodeInterpreter` `e2e-code-interpreter` in `agentcube` |

Warm-pool Go tests apply `e2e_code_interpreter_warmpool.yaml` at runtime (not in initial `kubectl apply` list in the shell script).

### Port forwards and health checks

- Workload manager: `kubectl port-forward svc/workloadmanager` → `WORKLOAD_MANAGER_LOCAL_PORT` (default **8080**) → pod 8080
- Router: `kubectl port-forward svc/agentcube-router` → `ROUTER_LOCAL_PORT` (default **8081**) → pod 8080
- Readiness: `curl` to `http://localhost:${WORKLOAD_MANAGER_LOCAL_PORT}/health` and `http://localhost:${ROUTER_LOCAL_PORT}/health/live`

### Auth for tests

- ServiceAccount `e2e-test` in `agentcube` + `ClusterRoleBinding` to `workloadmanager` clusterrole
- API token: `kubectl create token e2e-test -n agentcube --duration=24h` → `API_TOKEN`

### Python venv for E2E

- Directory: `E2E_VENV_DIR` (default `/tmp/agentcube-e2e-venv`)
- `python3 -m venv`, `pip install -e ./sdk-python`, verify `import agentcube`

### Test commands invoked by `run_e2e.sh`

**Go** (from repository root):

```bash
WORKLOAD_MANAGER_URL="http://localhost:${WORKLOAD_MANAGER_LOCAL_PORT}" \
ROUTER_URL="http://localhost:${ROUTER_LOCAL_PORT}" \
API_TOKEN=$API_TOKEN \
go test -v ./test/e2e/...
```

**Python** (after `cd` to `test/e2e`):

```bash
WORKLOAD_MANAGER_URL="..." ROUTER_URL="..." API_TOKEN=$API_TOKEN \
AGENTCUBE_NAMESPACE="${AGENTCUBE_NAMESPACE}" \
"$E2E_VENV_DIR/bin/python" test_codeinterpreter.py
```

(`test_codeinterpreter.py` uses `unittest.main()` and appends `--verbose` if missing.)

### Failure artifacts

On test failure, `collect_component_logs` writes under `ARTIFACTS_PATH` (CI: `${{ github.workspace }}/e2e-logs`): workload manager, router, and sandbox pod logs/describes.

---

## Test directory structure

```
test/
├── OWNERS
└── e2e/
    ├── README.md
    ├── __init__.py
    ├── run_e2e.sh
    ├── e2e_test.go
    ├── test_codeinterpreter.py
    ├── echo_agent.yaml
    ├── e2e_code_interpreter.yaml
    └── e2e_code_interpreter_warmpool.yaml
```

### Fixture paths (relative to repo root unless noted)

| Fixture | Description |
|---------|-------------|
| `test/e2e/echo_agent.yaml` | Echo `AgentRuntime` for router invocation tests |
| `test/e2e/e2e_code_interpreter.yaml` | Standard `CodeInterpreter` (`e2e-code-interpreter`, namespace `agentcube`) |
| `test/e2e/e2e_code_interpreter_warmpool.yaml` | `CodeInterpreter` with `warmPoolSize: 2` in `default` (loaded by Go tests from **package cwd** as `e2e_code_interpreter_warmpool.yaml`) |

---

## Go test commands and flags in CI

| Workflow / entrypoint | Command | Flags / notes |
|------------------------|---------|----------------|
| `test-coverage.yml` | `go test` | `-race -v -coverprofile=coverage.out -coverpkg=./pkg/... ./pkg/...` |
| `e2e.yml` via `make e2e` → `run_e2e.sh` | `go test` | `-v ./test/e2e/...` with env `WORKLOAD_MANAGER_URL`, `ROUTER_URL`, `API_TOKEN` |

---

## Python test commands in CI

| Workflow | Working dir | Command |
|----------|-------------|---------|
| `python-sdk-tests.yml` | `sdk-python` | `python -m pip install --upgrade pip`; `pip install pytest`; `pip install -e .`; `python -m pytest tests/ -v` |
| `e2e.yml` (via `run_e2e.sh`) | Invoked from `test/e2e/` | `"$E2E_VENV_DIR/bin/python" test_codeinterpreter.py` (unittest, verbosity 2) |

---

## Key Make targets referenced by CI

| Target | Referenced in | Role |
|--------|----------------|------|
| `docker-build` | `main.yml`, `run_e2e.sh` | Build workload manager image |
| `docker-build-router` | `run_e2e.sh` | Build router image |
| `docker-build-picod` | `run_e2e.sh` | Build picod image |
| `docker-buildx-push` | `build-push-release.yml` | Push workload manager image (`IMAGE_REGISTRY`, `WORKLOAD_MANAGER_IMAGE=workloadmanager:${TAG}`) |
| `docker-buildx-push-router` | `build-push-release.yml` | Push router image |
| `docker-buildx-push-picod` | `build-push-release.yml` | Push picod image |
| `e2e` | `e2e.yml` | Run `./test/e2e/run_e2e.sh` |
| `e2e-clean` | `e2e.yml` | `kind delete cluster --name $(E2E_CLUSTER_NAME)`; `rm -rf /tmp/agent-sandbox` |
| `lint` | `lint.yml` | `golangci-lint` (project default) |
| `gen-check` | `codegen-check.yml` | Verify generated code up to date |
| `gen-copyright` | `copyright-check.yml` | Generate copyright headers for check |

---

## Additional reference: E2E README vs script

`test/e2e/README.md` states Go **1.24+** and generic “install CRDs and agent-sandbox”; the **CI workflow** pins Go **1.23** for E2E, and **run_e2e.sh** pins **agent-sandbox `v0.1.1`** by default (overridable via `AGENT_SANDBOX_VERSION`).
