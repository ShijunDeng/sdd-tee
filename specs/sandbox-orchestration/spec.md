# Sandbox Orchestration Specification

## Purpose
Orchestrate agent sandboxes via Kubernetes CRDs (AgentRuntime, CodeInterpreter), a Gin HTTP API (workload manager), session persistence, garbage collection, and optional service-account authentication.

## Requirements

### Requirement: AgentRuntime CRD schema and API registration
The system SHALL expose a namespaced `AgentRuntime` custom resource in API group `runtime.agentcube.volcano.sh`, version `v1alpha1`, with subresource `status`, print column `Age` from `.metadata.creationTimestamp`, and SHALL register list kind `AgentRuntimeList`.

#### Scenario: Group version and resource naming
- **GIVEN** a Kubernetes API client resolving the CRD
- **WHEN** the group, version, and kind are read from type metadata
- **THEN** `GroupVersion` is `runtime.agentcube.volcano.sh/v1alpha1`, kind `AgentRuntime`, and GVR resource name is `agentruntimes`

### Requirement: AgentRuntime spec fields and kubebuilder rules
The system SHALL define `AgentRuntimeSpec` with: `Ports` as `[]TargetPort` serialized under JSON key `targetPort`; required `Template` (`*SandboxTemplate`) under JSON key `podTemplate`; required `SessionTimeout` (`*metav1.Duration`) under `sessionTimeout` with kubebuilder default `"15m"`; required `MaxSessionDuration` (`*metav1.Duration`) under `maxSessionDuration` with kubebuilder default `"8h"`.

#### Scenario: SandboxTemplate embeds Pod spec
- **GIVEN** an `AgentRuntime` with `spec.podTemplate`
- **WHEN** the template is deserialized
- **THEN** `labels` and `annotations` are optional maps and `spec` is required and of type `corev1.PodSpec`

### Requirement: AgentRuntime status
The system SHALL define `AgentRuntimeStatus` with optional `conditions` of type `[]metav1.Condition`.

#### Scenario: Conditions optional
- **GIVEN** a minimal `AgentRuntime` object
- **WHEN** status is omitted or empty
- **THEN** deserialization succeeds without requiring `conditions`

### Requirement: CodeInterpreter CRD schema
The system SHALL expose a namespaced `CodeInterpreter` CRD in the same API group/version with subresource `status` and print column `Age` from `.metadata.creationTimestamp`.

#### Scenario: CodeInterpreter GVR
- **GIVEN** dynamic client configuration for workload templates
- **WHEN** GVR is constructed for `codeinterpreters`
- **THEN** group is `runtime.agentcube.volcano.sh`, version `v1alpha1`, resource `codeinterpreters`

### Requirement: CodeInterpreterSpec fields
The system SHALL define `CodeInterpreterSpec` with: optional `Ports` (`[]TargetPort`, JSON `ports`); required `Template` (`*CodeInterpreterSandboxTemplate`, JSON `template`); optional `SessionTimeout` with default `"15m"`; optional `MaxSessionDuration` with default `"8h"`; optional `WarmPoolSize` (`*int32`); optional `AuthMode` (`AuthModeType`, JSON `authMode`) with default `"picod"` and enum `picod` or `none`.

#### Scenario: Auth mode constants
- **GIVEN** API constants for auth mode
- **WHEN** `AuthMode` is compared
- **THEN** `AuthModePicoD` equals `"picod"` and `AuthModeNone` equals `"none"`

### Requirement: CodeInterpreterStatus fields
The system SHALL define `CodeInterpreterStatus` with optional `conditions` and optional boolean `ready`.

#### Scenario: Ready flag
- **GIVEN** a reconciled `CodeInterpreter`
- **WHEN** status is updated by the controller
- **THEN** `status.ready` may be set to `true` alongside a `Ready` condition

### Requirement: TargetPort and Protocol types
The system SHALL define `TargetPort` with optional `pathPrefix`, optional `name`, required `port` (`uint32`), and required `protocol` (`ProtocolType`) with kubebuilder default `HTTP` and enum `HTTP` or `HTTPS`.

#### Scenario: Protocol constants
- **GIVEN** port configuration without explicit protocol in some code paths
- **WHEN** defaults apply at API level
- **THEN** default protocol is `HTTP` per kubebuilder marker

### Requirement: Workload manager health endpoint
The system SHALL serve `GET /health` without authentication and SHALL respond `200` with JSON body `{"status":"healthy"}`.

#### Scenario: Health bypasses auth middleware
- **GIVEN** `EnableAuth` is true
- **WHEN** a client calls `GET /health` with no `Authorization` header
- **THEN** the response status is 200 and body contains `"status":"healthy"`

### Requirement: Workload manager v1 routes and middleware
The system SHALL mount a `/v1` route group with `loggingMiddleware` then `authMiddleware` (order preserved), and SHALL register `POST /v1/agent-runtime`, `DELETE /v1/agent-runtime/sessions/:sessionId`, `POST /v1/code-interpreter`, and `DELETE /v1/code-interpreter/sessions/:sessionId`.

#### Scenario: Session id path parameter
- **GIVEN** a delete request
- **WHEN** Gin binds the path
- **THEN** the session identifier is read from parameter name `sessionId` (camelCase)

### Requirement: Create sandbox request validation
The system SHALL accept JSON for create endpoints matching `CreateSandboxRequest` with fields `kind`, `name`, `namespace`; SHALL overwrite `kind` from the handler (`AgentRuntime` or `CodeInterpreter`); and SHALL reject requests where `kind` is not one of those, `namespace` is empty, or `name` is empty.

#### Scenario: Validation failure returns 400
- **GIVEN** the handler sets `sandboxReq.Kind` from the route and `Validate()` is called
- **WHEN** `namespace` or `name` is empty in the JSON body
- **THEN** the response is 400 and the error message includes `required` (e.g. `namespace is required` or `name is required`)

### Requirement: Create sandbox success response
On successful creation the system SHALL respond `200` with `CreateSandboxResponse` containing `sessionId`, `sandboxId`, `sandboxName`, and `entryPoints` (each entry point has `path`, `protocol`, `endpoint`).

#### Scenario: Entry points reflect TargetPort and pod IP
- **GIVEN** a sandbox reaches running state and pod IP is resolved
- **WHEN** the response is built
- **THEN** each entry point `endpoint` is `host:port` joined from pod IP and configured port, with protocol string from `TargetPort.Protocol`

### Requirement: Create sandbox error responses
The system SHALL return `400` with `{"message":...}` for invalid JSON or validation failure; `404` with message from wrapped not-found errors when AgentRuntime or CodeInterpreter is missing from informer cache; `401` with message from client extraction error when `EnableAuth` is true; `500` with `{"message":"internal server error"}` for other create failures including timeout.

#### Scenario: JSON parse failure
- **GIVEN** a non-JSON body to `POST /v1/agent-runtime`
- **WHEN** the handler binds JSON
- **THEN** status is 400 and message is `Invalid request body`

### Requirement: Optional Bearer authentication via TokenReview
When `EnableAuth` is true, the system SHALL require header `Authorization: Bearer <token>` with exactly two space-separated fields; SHALL validate via `authentication/v1` `TokenReview` create; SHALL cache results in an LRU cache (capacity 1000, entry TTL 5 minutes); and SHALL store in context: token, full username, service account name, namespace parsed from `system:serviceaccount:<ns>:<name>`.

#### Scenario: Missing header
- **GIVEN** `EnableAuth` is true
- **WHEN** `/v1/...` is called without `Authorization`
- **THEN** response is 401 with message `Missing authorization header` and handler chain aborts

#### Scenario: TokenReview success path
- **GIVEN** a valid service account token and `EnableAuth` true
- **WHEN** `validateServiceAccountToken` runs with cache miss
- **THEN** the server creates `TokenReview` with `spec.token` set and uses `status.user.username` when `status.authenticated` is true

### Requirement: Authenticated Kubernetes operations use user client
When `EnableAuth` is true, the system SHALL use a per-user dynamic client (from bearer token) for creating/deleting `Sandbox` or `SandboxClaim` resources; when false, SHALL use the manager’s in-cluster/default dynamic client.

#### Scenario: User client cache key
- **GIVEN** repeated requests from the same namespace and service account name
- **WHEN** `GetOrCreateUserK8sClient` is used
- **THEN** the cache key is `<namespace>:<serviceAccountName>`

### Requirement: Sandbox creation ordering and store placeholder
The system SHALL call `StoreSandbox` with a placeholder `SandboxInfo` before creating the `Sandbox` or `SandboxClaim` in the API; SHALL register a one-shot watcher before create; SHALL wait up to 2 minutes for sandbox status `running` from the reconciler; SHALL resolve pod IP and then `UpdateSandbox` with full info; and SHALL roll back the created CR on failure after the wait (delete Sandbox or SandboxClaim within a 30s timeout context).

#### Scenario: Watcher registration before create
- **GIVEN** a create request reaches `createSandbox`
- **WHEN** the Sandbox CR is created
- **THEN** `WatchSandboxOnce` was already invoked for that namespace/name

#### Scenario: Timeout returns error
- **GIVEN** no running notification within 2 minutes
- **WHEN** the select completes
- **THEN** creation fails with error `sandbox creation timed out` and HTTP 500 is returned to the client

### Requirement: Pod IP resolution
The system SHALL prefer pod name equal to sandbox name; if annotation `agents.x-k8s.io/sandbox-pod-name` exists on the created Sandbox (from agent-sandbox controller), SHALL use that as pod name; SHALL load pod from informer cache and require `PodRunning` and non-empty `PodIP`; otherwise SHALL list pods by label `runtime.agentcube.io/sandbox-name=<sandboxName>` and pick the pod whose controller owner reference is kind `Sandbox` and name matches.

#### Scenario: Pod not running yields error
- **GIVEN** a matching pod in non-Running phase
- **WHEN** IP is resolved
- **THEN** resolution fails with an error indicating the pod is not running

### Requirement: Delete sandbox by session
The system SHALL load session from store by `sessionId`; on `ErrNotFound` return `404` with message `Session ID <id> not found, maybe already deleted`; delete `SandboxClaim` when stored `Kind` is `SandboxClaim`, else delete `Sandbox`; treat API `NotFound` on delete as success; then `DeleteSandboxBySessionID`; success response `200` `{"message":"Sandbox deleted successfully"}`.

#### Scenario: Store miss
- **GIVEN** no session key in store
- **WHEN** DELETE is invoked
- **THEN** HTTP status is 404 and message mentions the session id

### Requirement: Garbage collection loop
The system SHALL run a background goroutine tick every 15 seconds; each tick SHALL use a context timeout of 2 minutes; SHALL query inactive sessions with cutoff `now - 15m` and batch limit 16; SHALL query expired sessions with `before = now` and batch limit 16; SHALL merge lists and delete each unique workload then remove store entry by session ID.

#### Scenario: GC uses DefaultSandboxIdleTimeout
- **GIVEN** GC lists inactive sandboxes
- **WHEN** computing the inactive cutoff
- **THEN** `inactiveTime` equals `time.Now().Add(-DefaultSandboxIdleTimeout)` where `DefaultSandboxIdleTimeout` is 15 minutes

### Requirement: HTTP server and process behavior
The system SHALL use Gin with `gin.New()` for the workload API; SHALL serve with `h2c` wrapping and `http2.Server`; SHALL use `ReadTimeout` 15s and `IdleTimeout` 90s for HTTP when not using TLS; SHALL ping the store before listening; SHALL sync informers (AgentRuntime, CodeInterpreter, Pod) with up to 1 minute wait; on SIGINT/SIGTERM SHALL shutdown HTTP within 15s, cancel context, wait for background workers, then `Close()` the store.

#### Scenario: TLS requires cert and key
- **GIVEN** `EnableTLS` is true and cert or key path is empty
- **WHEN** `Start` runs
- **THEN** it returns an error that TLS is enabled but cert/key not provided

### Requirement: API error helper constants
The system SHALL define in package `api` the sentinel errors `ErrAgentRuntimeNotFound`, `ErrCodeInterpreterNotFound`, `ErrTemplateMissing`, `ErrPublicKeyMissing`, and SHALL map `CodeInterpreter` kind to group-resource `agentcube.volcano.sh/codeinterpreters` and default kinds to `agentcube.volcano.sh/agentruntimes` for `NewSandboxTemplateNotFoundError`.

#### Scenario: Session not found uses API machinery
- **GIVEN** `NewSessionNotFoundError("sid")`
- **WHEN** the error is inspected as `APIStatus`
- **THEN** the group resource is `agentcube.volcano.sh, Resource=sessions` and name is the session id
