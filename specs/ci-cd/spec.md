# CI/CD Specification

## Purpose
Automate validation on pull requests (build, lint, tests, codegen drift checks), publish container images on pushes to `main` and version tags, run end-to-end tests on Kind, exercise the Python SDK, and enforce spelling and copyright consistency.

## Requirements

### Requirement: Pull request build verification
The system SHALL build the Workload Manager Docker image on pull requests targeting `main` or `release-*` branches.

#### Scenario: Docker build in CI
- **GIVEN** a pull request to `main` or `release-*`
- **WHEN** the “Agentcube CI Workflow” job runs
- **THEN** it SHALL checkout the repository, set up Docker Buildx, verify `docker`/`buildx` versions, and run `make docker-build`

### Requirement: Go lint on changed Go code
The system SHALL run `make lint` (golangci-lint) when Go-related paths change on pull requests to `main` or `release-*`.

#### Scenario: Path-filtered lint
- **GIVEN** a pull request and path filter matches `**/*.go`, `go.mod`, `go.sum`, `.golangci.yml`, or `.github/workflows/lint.yml`
- **WHEN** the Lint workflow runs
- **THEN** it SHALL use Go `1.24` and execute `make lint`

### Requirement: Code generation check
The system SHALL verify generated artifacts match `make gen-all` when API, hack, workflow, or Makefile inputs change.

#### Scenario: Regenerate and diff
- **GIVEN** path filter matches `pkg/apis/**`, `hack/**`, `.github/workflows/**`, or `Makefile`
- **WHEN** the Codegen Check workflow runs with Go `1.24.4`
- **THEN** it SHALL run `make gen-check` (which runs `gen-all` and `git diff --exit-code`)

### Requirement: Go test coverage reporting
The system SHALL run race-enabled coverage tests on `pkg/...` for qualifying pull requests and merge groups, optionally uploading to Codecov.

#### Scenario: Coverage command
- **GIVEN** path filter `coverage` matches (broad glob excluding some media/docs per workflow)
- **WHEN** the Test Coverage job runs with Go `1.24`
- **THEN** it SHALL execute `go test -race -v -coverprofile=coverage.out -coverpkg=./pkg/... ./pkg/...` and upload `coverage.out` as an artifact

### Requirement: E2E testing on Kind
The system SHALL run `make e2e` in CI using a Kind-capable Ubuntu runner, capturing logs on failure.

#### Scenario: E2E job lifecycle
- **GIVEN** a pull request to `main` or `release-*`
- **WHEN** the E2E workflow runs
- **THEN** it SHALL set `ARTIFACTS_PATH=${{ github.workspace }}/e2e-logs`, install Kind tool `v0.30.0` (`install_only: true`), run `make e2e` with Go `1.23`, upload `e2e-logs` on failure, and always run `make e2e-clean`

### Requirement: Python SDK unit tests
The system SHALL run pytest for the SDK when `sdk-python/**` changes.

#### Scenario: Editable install and pytest
- **GIVEN** path filter matches `sdk-python/**`
- **WHEN** the Python SDK Tests job runs with Python `3.12` in `sdk-python/`
- **THEN** it SHALL `pip install pytest`, `pip install -e .`, and run `python -m pytest tests/ -v`

### Requirement: Python lint
The system SHALL run Ruff from repository root using `pyproject.toml` when Python-touching paths change.

#### Scenario: Ruff check
- **GIVEN** path filter matches `cmd/cli/**`, `sdk-python/**`, `example/**`, `test/**/*.py`, `pyproject.toml`, or the workflow file
- **WHEN** the Python Lint job runs with Python `3.10`
- **THEN** it SHALL `pip install ruff` and run `python3 -m ruff check . --config pyproject.toml`

### Requirement: Spelling check (codespell)
The system SHALL run codespell on the repository for pull requests to `main` or `release-*`, temporarily moving files that cause false positives.

#### Scenario: Codespell invocation
- **GIVEN** checkout complete
- **WHEN** codespell runs after backup/remove of `pyproject.toml`, `package-lock.json`, `package.json` at repo root (and nested copies per `find`)
- **THEN** it SHALL use `pip install codespell` and run codespell with `--check-filenames`, specified `--skip` globs, and `--ignore-words-list fo,nam,te,notin,NotIn` on `.`, then restore backed-up files

### Requirement: Copyright header check
The system SHALL ensure `make gen-copyright` produces no git diff when applicable files change.

#### Scenario: Copyright workflow
- **GIVEN** path filter marks `copyright` (all paths minus exclusions for md/svg/png/docs/.github per workflow)
- **WHEN** the job runs
- **THEN** it SHALL install `moreutils` (`sponge`), run `make gen-copyright`, and `git diff --exit-code`

### Requirement: Release image publication
The system SHALL build and push multi-architecture images for workloadmanager, router, and picod to GitHub Container Registry on pushes to `main` and on semantic version tags.

#### Scenario: Tag selects image tag
- **GIVEN** a `push` event
- **WHEN** `github.ref_type` is `tag`, environment `TAG` SHALL be `github.ref_name`; otherwise `TAG` SHALL be `latest`
- **THEN** the job SHALL log in to `ghcr.io` with `GITHUB_TOKEN` and run `make docker-buildx-push*`, setting `IMAGE_REGISTRY=ghcr.io/${{ github.repository_owner }}` and per-image `*_IMAGE=<name>:${TAG}`

### Requirement: Workflow approval for first-time contributors
The system SHALL optionally approve pending workflow runs for pull requests from repeat contributors or those labeled `ok-to-test`.

#### Scenario: Approve action_required runs
- **GIVEN** `pull_request_target` on `main` or `release-**` with label/sync events
- **WHEN** the contributor is not first-time (more than one PR) or PR has `ok-to-test`
- **THEN** the workflow SHALL list workflow runs for the head SHA with `status: action_required` and call `approveWorkflowRun` for each
