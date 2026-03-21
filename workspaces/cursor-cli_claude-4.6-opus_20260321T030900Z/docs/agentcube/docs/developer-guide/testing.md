---
sidebar_position: 5
---

# Testing

## Go unit tests

```bash
make test
# or
go test ./...
```

Run with race detector when debugging concurrency in Router or store code:

```bash
go test -race ./pkg/...
```

## Lint and format

```bash
make fmt
make vet
make lint        # golangci-lint
```

CI mirrors these targets in `.github/workflows/lint.yml` and related workflows.

## Python

The repository ships workflows for **Python lint** and **SDK tests** (`.github/workflows/python-lint.yml`, `python-sdk-tests.yml`). Locally:

```bash
pip install -e ./sdk-python[dev]  # if extras defined; else pip install pytest
pytest sdk-python
```

Use the same virtual environment for CLI and SDK development to catch integration issues early.

## End-to-end

`make e2e` runs the suite under `test/e2e/` when a cluster is configured. The placeholder test verifies wiring; expand this directory as scenarios mature.

## CRD / codegen drift

```bash
make gen-check
```

Fails if generated API or CRD YAML differs from committed output—run `make gen-all` after intentional API edits.

## Writing good tests

- Prefer **table-driven** tests for Router URL parsing, JWT claims, and store serialization.
- Mock the Kubernetes `Interface` for reconciler unit tests; reserve real API servers for e2e.
- For PicoD, use **httptest** with signed JWT fixtures to exercise middleware.
