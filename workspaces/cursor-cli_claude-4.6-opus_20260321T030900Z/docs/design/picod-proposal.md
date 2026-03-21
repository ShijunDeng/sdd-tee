# PicoD: In-Sandbox Daemon Proposal

## Overview

**PicoD** (Pico Daemon) is a minimal HTTP service that runs **inside** each code-interpreter (or tool) sandbox. It exposes a stable **execution and file API** so the control plane and SDKs can run commands and manage workspace artifacts **without** SSH or ad hoc sidecars.

Binary: `cmd/picod/main.go`  
HTTP stack: Gin (`pkg/picod/server.go`)

## Responsibilities

1. **Execute processes** — Run shell commands with optional working directory and timeout.
2. **File management** — Upload, list, download, and text write within a configured workspace root.
3. **Health** — `GET /health` returns plain `ok` for kubelet or sidecar probes.

## Execute API

**`POST /api/execute`**

JSON body (`ExecuteRequest`):

| Field | Type | Description |
|-------|------|-------------|
| `command` | `[]string` | argv-style command (preferred) or shell pipeline per deployment convention |
| `timeout` | string | Optional Go duration string; default bounded (e.g. 60s) |
| `cwd` | string | Optional working directory under workspace |

Response (`ExecuteResponse`):

- `stdout`, `stderr` — captured output
- `exitCode` — process exit code
- `timedOut` — true when deadline exceeded (exit code may mirror `timeout(1)` convention, e.g. `124`)

## File APIs

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/files` | Multipart upload (`path` + `file`) |
| `GET` | `/api/files` | List directory (query path, default `.`) |
| `GET` | `/api/files/*path` | Download file |

Additional helpers may exist for text write via JSON POST routes proxied from the Router (SDK uses `write-file`, `upload-file`, `download-file` under the code-interpreter invocation prefix).

## Configuration

- **Listen port** — from `Config.Port` (must be > 0).
- **Workspace** — `Config.Workspace` (required); all file operations must stay within this tree (implementation should reject `..` traversal).
- **`PICOD_AUTH_PUBLIC_KEY`** — Required PEM for JWT verification on `/api/*`.

## Security

1. **JWT on all API routes** (except `/health`) — Bearer RS256 tokens signed by the Router; see `PicoD-Plain-Authentication-Design.md`.
2. **Workspace confinement** — File handlers resolve paths relative to the workspace root; deny escapes.
3. **Timeouts** — Prevent runaway interpreter or fork bombs from hanging the daemon.
4. **Resource limits** — Sandbox `Pod` should set CPU/memory limits; PicoD inherits cgroup constraints.

## Interaction with Router

The Router reverse-proxies authenticated invocation traffic to the Pod IP / Service backing the session. PicoD never talks to Kubernetes; it only trusts **cryptographic** identity on each request.

## Operational notes

- Image: `docker/Dockerfile.picod` (multi-stage build in repo).
- Logging: structured logs via klog in surrounding binaries; Gin recovery middleware catches panics.

## Future work

- Optional **mTLS** between Router and Pod for double encryption in multi-tenant clusters.
- Per-session Unix user drop (non-root container + user namespace) where RuntimeClass allows.
