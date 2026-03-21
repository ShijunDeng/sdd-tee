# Copilot / AI assistant guidelines — AgentCube

This repository implements **AgentCube** (`github.com/volcano-sh/agentcube`): a control plane and data plane for agent sandboxes (router, workload manager, PicoD, agentd).

## Project layout
- `cmd/` — binaries (`router`, `workload-manager`, `picod`, `agentd`)
- `pkg/` — shared libraries; prefer extending existing patterns over new frameworks
- `docker/` — container images
- `manifests/` — Kubernetes manifests
- `sdk-python/` — Python SDK

## Go conventions
- Module: `github.com/volcano-sh/agentcube`; Go **1.24** per `go.mod`
- Use the **standard `testing` package**; **testify** is acceptable for assertions in tests
- Keep changes minimal and scoped; match naming and structure of neighboring files
- Kubernetes code: prefer `client-go` fakes / envtest patterns for unit tests; avoid broad refactors to generated client stubs under `client-go/` unless the task requires it

## API / HTTP
- Router and workload manager use **Gin**; PicoD uses Gin with JWT middleware
- Do not log secrets or bearer tokens

## Python SDK
- Type hints and `pyrightconfig.json` at repo root target `sdk-python/`

When unsure, read adjacent code and mirror its style before adding new abstractions.
