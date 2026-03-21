# Router Proposal: Session-Aware Edge HTTP

## Role

The **Router** is the **edge HTTP control plane** for AgentCube. It exposes versioned REST paths for **agent runtimes** and **code interpreters**, resolves active sessions, and **reverse-proxies** requests to the correct sandbox backend while enforcing **JWT authentication** for PicoD and **global concurrency** limits.

Implementation: `pkg/router/server.go`, `cmd/router/main.go`.

## API surface

Invocation routes (Gin):

- `GET|POST /v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path`
- `GET|POST /v1/namespaces/:namespace/code-interpreters/:name/invocations/*path`

The trailing `*path` is forwarded to the backend (e.g. PicoD `/api/...` or agent HTTP server paths).

## Session management

- **`SessionManager`** (`pkg/router/session.go`) coordinates session lifecycle with the **store** (Redis/Valkey).
- Sessions bind **namespace**, runtime or interpreter **name**, and client-facing **session identifiers** to backend **upstream URLs** (Pod/Service endpoints).
- Idle and maximum durations originate from **AgentRuntime** / **CodeInterpreter** CRs and are enforced cooperatively by controllers and session TTL in the store.

## Reverse proxy

- Uses `httputil.ReverseProxy` to stream request/response bodies.
- Upstream base URL is chosen after session lookup; path rewriting preserves the suffix after `/invocations/`.
- For PicoD-backed flows, the Router may inject **`Authorization: Bearer <jwt>`** using `JWTManager` so PicoD can validate RS256 tokens.

## JWT authentication

- `JWTManager` maintains RSA keys in Secret **`picod-router-identity`** (see `PicoD-Plain-Authentication-Design.md`).
- Tokens are **short-lived** and scoped to the invocation context.
- Issuer: `agentcube-router`.

## Concurrency control

- A **weighted semaphore** (`golang.org/x/sync/semaphore`) caps concurrent in-flight requests (`Config.maxConcurrent()`).
- When the limit is exceeded, the Router returns **`429 Too Many Requests`** with JSON `{"error":"max concurrent requests exceeded"}`.

Operators tune this to protect sandboxes and shared Redis from thundering herds.

## Health and readiness

| Path | Meaning |
|------|---------|
| `GET /health/live` | Liveness — always OK if process up |
| `GET /health/ready` | Readiness — may check store connectivity |
| `/healthz`, `/readyz` | Compatibility aliases (logging may filter these) |

## TLS

- Optional TLS via `Config.EnableTLS` with certificate and key paths for clusters that terminate TLS inside the Router pod instead of at Ingress.

## Dependencies

- **Redis / Valkey** — Session and routing metadata (`pkg/store`).
- **Kubernetes client** — JWT identity Secret management.

## Deployment

Helm template: `manifests/charts/base/templates/agentcube-router.yaml`  
Image default: `ghcr.io/volcano-sh/agentcube-router:latest`

## Future enhancements

- Per-runtime concurrency budgets instead of a single global semaphore.
- OpenTelemetry tracing across Router → Workload Manager → sandbox.
- OAuth2/OIDC at the edge for **human** operators, distinct from PicoD service JWTs.
