# Session Routing Specification

## Purpose
Route HTTP invocation traffic to sandboxes by session: resolve or create sessions via the workload manager, track activity in the store, reverse-proxy to pod endpoints, and sign outbound requests with JWT when targeting sandboxes.

## Requirements

### Requirement: Session resolution and creation
The system SHALL read session id from request header `x-agentcube-session-id`. When the header is empty, the system SHALL POST to the workload manager to create a sandbox. When non-empty, the system SHALL load `SandboxInfo` from the store by session id.

#### Scenario: Missing session triggers workload manager create
- **GIVEN** `WORKLOAD_MANAGER_URL` is set and an invocation request has no `x-agentcube-session-id`
- **WHEN** `GetSandboxBySession` runs for `AgentRuntimeKind`
- **THEN** the client POSTs JSON `{"kind":"AgentRuntime","name":...,"namespace":...}` to `{WORKLOAD_MANAGER_URL}/v1/agent-runtime`

#### Scenario: Unknown session returns not found
- **GIVEN** a non-empty session id not present in store
- **WHEN** the store returns `ErrNotFound`
- **THEN** the error maps to `NewSessionNotFoundError(sessionID)` and the HTTP handler responds using API status (typically 404)

### Requirement: Workload manager URL and auth token for creates
The system SHALL require environment variable `WORKLOAD_MANAGER_URL` at session manager construction (non-empty). When the file `/var/run/secrets/kubernetes.io/serviceaccount/token` exists and is readable, the system SHALL attach `Authorization: Bearer <trimmed contents>` to create requests.

#### Scenario: Missing WORKLOAD_MANAGER_URL fails startup
- **GIVEN** `WORKLOAD_MANAGER_URL` is unset
- **WHEN** `NewSessionManager` is called
- **THEN** it returns error `WORKLOAD_MANAGER_URL environment variable is not set`

### Requirement: Create response validation
The system SHALL accept workload manager HTTP 200 with body `CreateSandboxResponse`; SHALL reject with internal error if `sessionId` in body is empty; SHALL build in-memory `SandboxInfo` with `SandboxID`, `Name` (= `sandboxName`), `SessionID`, `EntryPoints` from the response (other fields may be zero).

#### Scenario: Non-OK from workload manager
- **GIVEN** workload manager returns HTTP 404
- **WHEN** the session manager handles the response
- **THEN** the error is `NewSandboxTemplateNotFoundError(namespace, name, kind)`

### Requirement: Reverse proxy to sandbox
The system SHALL determine upstream URL from `SandboxInfo.EntryPoints` by first matching `path` prefix against the invocation path; if none match, SHALL use the first entry point. The system SHALL build URL by prefixing `protocol` (lowercase) and `://` to `endpoint` when protocol is set and endpoint lacks a scheme. The system SHALL use `httputil.NewSingleHostReverseProxy`, shared `http.Transport` on the proxy, and custom `Director` to set path, host, forwarding headers, and optional JWT.

#### Scenario: No entry points
- **GIVEN** `EntryPoints` is empty
- **WHEN** upstream is determined
- **THEN** the handler responds 404 JSON `{"error":"no entry point found for sandbox"}`

### Requirement: JWT injection for sandbox kinds
For sandbox kinds `Sandbox` and `SandboxClaim`, the system SHALL generate a JWT before proxying and SHALL set `Authorization: Bearer <token>` on the proxied request.

#### Scenario: Signing failure
- **GIVEN** JWT generation returns an error
- **WHEN** forwarding is attempted
- **THEN** the handler responds 500 with JSON containing `"code":"JWT_SIGNING_FAILED"` and `"error":"failed to sign request"`

### Requirement: Forwarding headers and response header
The system SHALL set `X-Forwarded-Host` from the incoming request host, `X-Forwarded-Proto` to `https` when TLS is present else `http`, and `X-Forwarded-For` by appending client IP to any existing values. The system SHALL set response header `x-agentcube-session-id` to the resolved session id on all proxied responses.

#### Scenario: Path normalization
- **GIVEN** the Gin path param is non-empty and lacks a leading slash
- **WHEN** the director runs
- **THEN** the outbound path is prefixed with `/`

### Requirement: Proxy error mapping
The system SHALL map proxy errors containing `connection refused` to 502 `{"error":"sandbox unreachable"}`, containing `timeout` to 504 `{"error":"sandbox timeout"}`, and other errors to 502 `{"error":"sandbox unreachable"}`.

#### Scenario: Downstream connection refused
- **GIVEN** the reverse proxy fails with an error whose message includes `connection refused`
- **WHEN** `ErrorHandler` runs
- **THEN** status is 502 and error text is `sandbox unreachable`

### Requirement: Last-activity updates
The system SHALL call `UpdateSessionLastActivity` with `time.Now()` after successfully resolving the sandbox and again after `forwardToSandbox` returns (twice per successful invoke path). Failures SHALL be logged as warnings only.

#### Scenario: Store update failure does not block proxy
- **GIVEN** `UpdateSessionLastActivity` returns an error
- **WHEN** handling continues
- **THEN** the proxy still runs if sandbox resolution succeeded

### Requirement: Health endpoints
The system SHALL expose `GET /health/live` returning 200 `{"status":"alive"}`. The system SHALL expose `GET /health/ready` returning 200 `{"status":"ready"}` when session manager is non-nil, else 503 with `status` and `error` fields.

#### Scenario: Ready depends on session manager
- **GIVEN** `sessionManager` is nil
- **WHEN** `GET /health/ready` is served
- **THEN** status is 503 and body includes `"error":"session manager not available"`

### Requirement: Concurrency limiting
The system SHALL apply a semaphore middleware to `/v1/*` routes with capacity `MaxConcurrentRequests` (default 1000 when config value ≤ 0). When no slot is available, the system SHALL respond 429 JSON `{"error":"server overloaded, please try again later","code":"SERVER_OVERLOADED"}` and abort.

#### Scenario: Default limit when zero in config
- **GIVEN** `NewServer` receives `MaxConcurrentRequests` 0
- **WHEN** the server is constructed
- **THEN** the effective limit is set to 1000 before route registration

### Requirement: Invocation route surface
The system SHALL register GET and POST for `/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path` and for `/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path`, with Gin logger, recovery, and concurrency middleware on the `/v1` group only.

#### Scenario: Kind passed to session lookup
- **GIVEN** agent-runtime invocation
- **WHEN** `handleInvoke` runs
- **THEN** kind argument is `AgentRuntime` (`types.AgentRuntimeKind`)

### Requirement: HTTP server behavior
The system SHALL serve with `h2c` and `http2.Server`, `ReadTimeout` 30s, `IdleTimeout` 90s; on context cancel SHALL shutdown within 10s. Optional TLS SHALL require both cert and key paths.

#### Scenario: TLS misconfiguration
- **GIVEN** `EnableTLS` true and empty cert path
- **WHEN** `Start` runs
- **THEN** it returns error stating cert/key not provided

### Requirement: Identity secret bootstrap for JWT
On server creation the system SHALL construct `JWTManager`, call `TryStoreOrLoadJWTKeySecret`, and fail server creation if that returns error (except in-cluster skip path returns nil when not in cluster).

#### Scenario: In-cluster secret creation
- **GIVEN** in-cluster config succeeds and secret does not exist
- **WHEN** `TryStoreOrLoadJWTKeySecret` runs
- **THEN** it creates opaque secret `picod-router-identity` in namespace from `AGENTCUBE_NAMESPACE` or `default` with keys `private.pem` and `public.pem`
