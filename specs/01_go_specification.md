# AgentCube Go Specification

*Generated: 2026-03-21T07:44:15Z (UTC) — derived from source tree `/tmp/agentcube-ref`.*

This document records observable behavior, types, HTTP contracts, and operational parameters as implemented in the AgentCube Go codebase.

---

## 1. Module and dependencies

| Item | Value |
|------|--------|
| **Module path** | `github.com/volcano-sh/agentcube` |
| **Go version** | `1.24.4` |
| **Toolchain** | `go1.24.9` |

### 1.1 Direct `require` dependencies (from `go.mod`)

| Module | Version |
|--------|---------|
| `github.com/agiledragon/gomonkey/v2` | v2.13.0 |
| `github.com/alicebob/miniredis/v2` | v2.35.0 |
| `github.com/gin-gonic/gin` | v1.10.0 |
| `github.com/golang-jwt/jwt/v5` | v5.2.2 |
| `github.com/google/uuid` | v1.6.0 |
| `github.com/redis/go-redis/v9` | v9.17.1 |
| `github.com/stretchr/testify` | v1.11.1 |
| `github.com/valkey-io/valkey-go` | v1.0.69 |
| `golang.org/x/net` | v0.47.0 |
| `k8s.io/api` | v0.34.1 |
| `k8s.io/apimachinery` | v0.34.1 |
| `k8s.io/client-go` | v0.34.1 |
| `k8s.io/klog/v2` | v2.130.1 |
| `k8s.io/utils` | v0.0.0-20251002143259-bc988d571ff4 |
| `sigs.k8s.io/agent-sandbox` | v0.1.1 |
| `sigs.k8s.io/controller-runtime` | v0.22.2 |

*(Indirect dependencies are listed in `go.mod` but omitted here for length.)*

---

## 2. CRD API (`pkg/apis/runtime/v1alpha1`)

### 2.1 API group and version

| Constant / variable | Value |
|---------------------|--------|
| **Group** | `runtime.agentcube.volcano.sh` |
| **Version** | `v1alpha1` |
| `GroupVersion` | `schema.GroupVersion{Group: "runtime.agentcube.volcano.sh", Version: "v1alpha1"}` |
| **Kubebuilder groupName** | `runtime.agentcube.volcano.sh` |

### 2.2 Kubernetes resource names (GVR)

| Resource | Group | Version | Plural resource |
|----------|-------|---------|-----------------|
| AgentRuntime | `runtime.agentcube.volcano.sh` | `v1alpha1` | `agentruntimes` |
| CodeInterpreter | `runtime.agentcube.volcano.sh` | `v1alpha1` | `codeinterpreters` |

### 2.3 `AgentRuntime`

**Markers:** `+genclient`, `+k8s:deepcopy-gen:interfaces=k8s.io/apimachinery/pkg/runtime.Object`, `+kubebuilder:object:root=true`, `+kubebuilder:subresource:status`, `+kubebuilder:resource:scope=Namespaced`, print column Age → `.metadata.creationTimestamp`.

| Field | Go type | JSON tag | Kubebuilder / notes |
|-------|---------|----------|---------------------|
| Embedded `TypeMeta` | `metav1.TypeMeta` | `json:",inline"` | — |
| Embedded `ObjectMeta` | `metav1.ObjectMeta` | `json:"metadata,omitempty"` | — |
| `Spec` | `AgentRuntimeSpec` | `json:"spec"` | — |
| `Status` | `AgentRuntimeStatus` | `json:"status,omitempty"` | subresource |

#### `AgentRuntimeSpec`

| Field | Go type | JSON tag | Kubebuilder / notes |
|-------|---------|----------|---------------------|
| `Ports` | `[]TargetPort` | `json:"targetPort"` | — |
| `Template` | `*SandboxTemplate` | `json:"podTemplate"` | Required |
| `SessionTimeout` | `*metav1.Duration` | `json:"sessionTimeout,omitempty"` | Required; **default** `"15m"` |
| `MaxSessionDuration` | `*metav1.Duration` | `json:"maxSessionDuration,omitempty"` | Required; **default** `"8h"` |

#### `AgentRuntimeStatus`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Conditions` | `[]metav1.Condition` | `json:"conditions,omitempty"` |

*`metav1.Condition` uses upstream Kubernetes JSON field names: `type`, `status`, `observedGeneration`, `lastTransitionTime`, `reason`, `message` (see `k8s.io/apimachinery/pkg/apis/meta/v1`).*

#### `SandboxTemplate`

| Field | Go type | JSON tag | Kubebuilder |
|-------|---------|----------|-------------|
| `Labels` | `map[string]string` | `json:"labels,omitempty"` | optional |
| `Annotations` | `map[string]string` | `json:"annotations,omitempty"` | optional |
| `Spec` | `corev1.PodSpec` | `json:"spec"` | Required |

#### `AgentRuntimeList`

| Field | Go type | JSON tag |
|-------|---------|----------|
| Embedded `TypeMeta` | `metav1.TypeMeta` | `json:",inline"` |
| Embedded `ListMeta` | `metav1.ListMeta` | `json:"metadata,omitempty"` |
| `Items` | `[]AgentRuntime` | `json:"items"` |

### 2.4 `CodeInterpreter`

**Markers:** same pattern as `AgentRuntime` (root, status subresource, namespaced, genclient, deepcopy).

| Field | Go type | JSON tag |
|-------|---------|----------|
| Embedded `TypeMeta` | `metav1.TypeMeta` | `json:",inline"` |
| Embedded `ObjectMeta` | `metav1.ObjectMeta` | `json:"metadata,omitempty"` |
| `Spec` | `CodeInterpreterSpec` | `json:"spec"` |
| `Status` | `CodeInterpreterStatus` | `json:"status,omitempty"` |

#### `CodeInterpreterSpec`

| Field | Go type | JSON tag | Kubebuilder / notes |
|-------|---------|----------|---------------------|
| `Ports` | `[]TargetPort` | `json:"ports,omitempty"` | optional |
| `Template` | `*CodeInterpreterSandboxTemplate` | `json:"template"` | Required |
| `SessionTimeout` | `*metav1.Duration` | `json:"sessionTimeout,omitempty"` | **default** `"15m"` |
| `MaxSessionDuration` | `*metav1.Duration` | `json:"maxSessionDuration,omitempty"` | **default** `"8h"` |
| `WarmPoolSize` | `*int32` | `json:"warmPoolSize,omitempty"` | optional |
| `AuthMode` | `AuthModeType` | `json:"authMode,omitempty"` | **default** `"picod"`; Enum `picod`; `none` |

#### `CodeInterpreterStatus`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Conditions` | `[]metav1.Condition` | `json:"conditions,omitempty"` |
| `Ready` | `bool` | `json:"ready,omitempty"` |

#### `CodeInterpreterSandboxTemplate`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Labels` | `map[string]string` | `json:"labels,omitempty"` |
| `Annotations` | `map[string]string` | `json:"annotations,omitempty"` |
| `RuntimeClassName` | `*string` | `json:"runtimeClassName,omitempty"` |
| `Image` | `string` | `json:"image,omitempty"` |
| `ImagePullPolicy` | `corev1.PullPolicy` | `json:"imagePullPolicy,omitempty"` |
| `ImagePullSecrets` | `[]corev1.LocalObjectReference` | `json:"imagePullSecrets,omitempty"` |
| `Environment` | `[]corev1.EnvVar` | `json:"environment,omitempty"` |
| `Command` | `[]string` | `json:"command,omitempty"` |
| `Args` | `[]string` | `json:"args,omitempty"` |
| `Resources` | `corev1.ResourceRequirements` | `json:"resources,omitempty"` |

#### `TargetPort`

| Field | Go type | JSON tag | Kubebuilder |
|-------|---------|----------|-------------|
| `PathPrefix` | `string` | `json:"pathPrefix,omitempty"` | optional |
| `Name` | `string` | `json:"name,omitempty"` | optional |
| `Port` | `uint32` | `json:"port"` | — |
| `Protocol` | `ProtocolType` | `json:"protocol"` | **default** `HTTP`; Enum `HTTP`; `HTTPS` |

#### `AuthModeType` (`string`)

| Constant | Value |
|----------|--------|
| `AuthModePicoD` | `"picod"` |
| `AuthModeNone` | `"none"` |

#### `ProtocolType` (`string`)

| Constant | Value |
|----------|--------|
| `ProtocolTypeHTTP` | `"HTTP"` |
| `ProtocolTypeHTTPS` | `"HTTPS"` |

#### `CodeInterpreterList`

| Field | Go type | JSON tag |
|-------|---------|----------|
| Embedded `TypeMeta` / `ListMeta` | — | `json:",inline"` / `json:"metadata,omitempty"` |
| `Items` | `[]CodeInterpreter` | `json:"items"` |

### 2.5 Register-time kind metadata (`register.go`)

| Name | Expression / value |
|------|-------------------|
| `CodeInterpreterKind` | `"CodeInterpreter"` |
| `CodeInterpreterListKind` | `"CodeInterpreterList"` |
| `CodeInterpreterGroupVersionKind` | `GroupVersion.WithKind("CodeInterpreter")` |
| `AgentRuntimeKind` | `"AgentRuntime"` |
| `AgentRuntimeListKind` | `"AgentRuntimeList"` |
| `AgentRuntimeGroupVersionKind` | `GroupVersion.WithKind("AgentRuntime")` |
| `SchemeGroupVersion` | alias of `GroupVersion` |

---

## 3. Shared types (`pkg/common/types`)

### 3.1 Exported string constants

| Constant | Value | Meaning in code |
|----------|--------|-----------------|
| `AgentRuntimeKind` | `AgentRuntime` | Router / WM kind string |
| `CodeInterpreterKind` | `CodeInterpreter` | Router / WM kind string |
| `SandboxKind` | `Sandbox` | Underlying CR kind for direct Sandbox |
| `SandboxClaimsKind` | `SandboxClaim` | Warm-pool path uses SandboxClaim |

### 3.2 `SandboxInfo`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Kind` | `string` | `json:"kind"` |
| `SandboxID` | `string` | `json:"sandboxId"` |
| `SandboxNamespace` | `string` | `json:"sandboxNamespace"` |
| `Name` | `string` | `json:"name"` |
| `EntryPoints` | `[]SandboxEntryPoint` | `json:"entryPoints"` |
| `SessionID` | `string` | `json:"sessionId"` |
| `CreatedAt` | `time.Time` | `json:"createdAt"` |
| `ExpiresAt` | `time.Time` | `json:"expiresAt"` |
| `Status` | `string` | `json:"status"` |

### 3.3 `SandboxEntryPoint`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Path` | `string` | `json:"path"` |
| `Protocol` | `string` | `json:"protocol"` |
| `Endpoint` | `string` | `json:"endpoint"` |

### 3.4 `CreateSandboxRequest`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Kind` | `string` | `json:"kind"` |
| `Name` | `string` | `json:"name"` |
| `Namespace` | `string` | `json:"namespace"` |

**`Validate()`:** `Kind` must be `AgentRuntime` or `CodeInterpreter`; `Namespace` and `Name` non-empty.

### 3.5 `CreateSandboxResponse`

| Field | Go type | JSON tag |
|-------|---------|----------|
| `SessionID` | `string` | `json:"sessionId"` |
| `SandboxID` | `string` | `json:"sandboxId"` |
| `SandboxName` | `string` | `json:"sandboxName"` |
| `EntryPoints` | `[]SandboxEntryPoint` | `json:"entryPoints"` |

---

## 4. API helpers and errors (`pkg/api`)

### 4.1 Package constants

| Name | Value |
|------|--------|
| `resourceGroup` | `agentcube.volcano.sh` |
| `sessionResourceName` | `sessions` |
| `agentRuntimeResourceName` | `agentruntimes` |
| `codeInterpreterResourceName` | `codeinterpreters` |

### 4.2 Sentinel `error` values

| Variable | Message / use |
|----------|----------------|
| `ErrAgentRuntimeNotFound` | `errors.New("agent runtime not found")` |
| `ErrCodeInterpreterNotFound` | `errors.New("code interpreter not found")` |
| `ErrTemplateMissing` | `errors.New("resource has no pod template")` |
| `ErrPublicKeyMissing` | `errors.New("public key not yet loaded from Router Secret")` |

### 4.3 Constructor functions (return `error`, often `k8s.io/apimachinery/pkg/api/errors`)

| Function | Returns |
|----------|---------|
| `NewSessionNotFoundError(sessionID string)` | `apierrors.NewNotFound` for GR `{Group: agentcube.volcano.sh, Resource: sessions}` |
| `NewSandboxTemplateNotFoundError(namespace, name, kind string)` | `apierrors.NewNotFound` for `agentruntimes` or `codeinterpreters` GR |
| `NewUpstreamUnavailableError(err error)` | `apierrors.NewServiceUnavailable` |
| `NewInternalError(err error)` | `apierrors.NewInternalError` |

---

## 5. Store (`pkg/store`)

### 5.1 `Store` interface (exact signatures)

```go
type Store interface {
    Ping(ctx context.Context) error
    GetSandboxBySessionID(ctx context.Context, sessionID string) (*types.SandboxInfo, error)
    StoreSandbox(ctx context.Context, sandboxStore *types.SandboxInfo) error
    UpdateSandbox(ctx context.Context, sandboxStore *types.SandboxInfo) error
    DeleteSandboxBySessionID(ctx context.Context, sessionID string) error
    ListExpiredSandboxes(ctx context.Context, before time.Time, limit int64) ([]*types.SandboxInfo, error)
    ListInactiveSandboxes(ctx context.Context, before time.Time, limit int64) ([]*types.SandboxInfo, error)
    UpdateSessionLastActivity(ctx context.Context, sessionID string, at time.Time) error
    Close() error
}
```

### 5.2 Store errors

| Name | Type | Value |
|------|------|--------|
| `ErrNotFound` | `error` | `errors.New("store: not found")` |

### 5.3 Singleton and `STORE_TYPE`

| Constant | Value |
|----------|--------|
| `redisStoreType` | `redis` |
| `valkeyStoreType` | `valkey` |

- `Storage()` initializes once via `sync.Once`; on failure calls `klog.Fatalf`.
- Env `STORE_TYPE`: case-insensitive; if unset, **default `redis`**.

### 5.4 Redis implementation

**Env vars**

| Variable | Required | Notes |
|----------|----------|--------|
| `REDIS_ADDR` | yes | — |
| `REDIS_PASSWORD` | yes by default | If `REDIS_PASSWORD_REQUIRED` is not exactly `false` (case-insensitive), empty password is rejected |
| `REDIS_PASSWORD_REQUIRED` | no | Set to `false` to allow empty password |

**Key layout**

| Key / pattern | Purpose |
|---------------|---------|
| `session:{sessionID}` | JSON blob of `types.SandboxInfo` |
| `session:expiry` | ZSET; score = `ExpiresAt.Unix()`; member = sessionID |
| `session:last_activity` | ZSET; score = last activity unix; member = sessionID |

**Behavior notes**

- `StoreSandbox`: `SETNX` on session key, `ZADD` expiry + last_activity; requires non-zero `ExpiresAt`.
- `UpdateSandbox`: `SET` with `XX` only (no index update).
- `ListExpiredSandboxes` / `ListInactiveSandboxes`: `ZRANGEBYSCORE` with `-inf` to `before.Unix()`, `LIMIT 0 limit`; returns `nil` if `limit <= 0`.
- `UpdateSessionLastActivity`: `GET` session key first; missing → `ErrNotFound`; then `ZADD` last_activity.

### 5.5 Valkey implementation

**Env vars**

| Variable | Required | Notes |
|----------|----------|--------|
| `VALKEY_ADDR` | yes | Comma-separated addresses → `strings.Split(..., ",")` |
| `VALKEY_PASSWORD` | yes by default | Same `VALKEY_PASSWORD_REQUIRED=false` escape as Redis |
| `VALKEY_DISABLE_CACHE` | no | If parseable bool `true` → `ClientOption.DisableCache = true` |
| `VALKEY_FORCE_SINGLE` | no | If parseable bool `true` → `ClientOption.ForceSingleClient = true` |

**Key layout:** same logical names as Redis (`session:`, `session:expiry`, `session:last_activity`).

**Behavior:** analogous to Redis (`SETNX` + `ZADD` multi, `SET XX`, `ZREM` on delete, `ZRANGEBYSCORE` with `LIMIT`, `EXISTS` before last-activity update).

---

## 6. Workload Manager (`pkg/workloadmanager`)

### 6.1 HTTP server

- Framework: **Gin**; root engine `gin.New()` (no default logger/recovery on root).
- **HTTP/2 cleartext:** `golang.org/x/net/http2` + `h2c.NewHandler`.
- **Listen address:** `":" + config.Port`.
- **Timeouts:** `ReadTimeout` 15s, `IdleTimeout` 90s.

### 6.2 Routes

| Method | Path | Auth | Handler / behavior |
|--------|------|------|---------------------|
| `GET` | `/health` | None | JSON `{"status":"healthy"}` |
| `POST` | `/v1/agent-runtime` | See §6.3 | Create sandbox for `AgentRuntime` |
| `DELETE` | `/v1/agent-runtime/sessions/:sessionId` | See §6.3 | Delete by session |
| `POST` | `/v1/code-interpreter` | See §6.3 | Create sandbox for `CodeInterpreter` |
| `DELETE` | `/v1/code-interpreter/sessions/:sessionId` | See §6.3 | Delete by session |

**`/v1/*` middleware order:** `loggingMiddleware` → `authMiddleware`.

### 6.3 Authentication (`auth.go`)

- If `Config.EnableAuth == false`: no check.
- If enabled:
  - Header `Authorization: Bearer <token>` required.
  - Token validated via Kubernetes **`TokenReview`** (`AuthenticationV1().TokenReviews().Create`).
  - Username must parse as `system:serviceaccount:<namespace>:<serviceaccount-name>`.
  - Context keys (private type `contextKey`): `userToken`, `serviceAccount`, `serviceAccountName`, `namespace`.
- **Token cache:** `NewTokenCache(1000, 5*time.Minute)` — LRU-ish list + map; entries expire after 5 minutes from `lastAccess`.

### 6.4 Request / response bodies (JSON)

**Success and error envelope**

- Success: arbitrary JSON via `c.JSON`.
- Error helper `respondError` → `ErrorResponse` `{ "message": string }` with given status.

**`POST /v1/agent-runtime` and `POST /v1/code-interpreter`**

- **Request body:** `CreateSandboxRequest` (see §3.4). Handler sets `Kind` from route.
- **Response 200:** `CreateSandboxResponse` (§3.5).
- **400:** invalid JSON / validation message in `message`.
- **401:** auth failures when `EnableAuth` (create/delete).
- **404:** agent runtime or code interpreter not in informer cache (`ErrAgentRuntimeNotFound` / `ErrCodeInterpreterNotFound`).
- **500:** internal errors, timeouts.

**`DELETE .../sessions/:sessionId`**

- **Response 200:** `{"message":"Sandbox deleted successfully"}`.
- **404:** store `ErrNotFound` → message includes session id.
- **401:** when auth enabled and user client extraction fails.

### 6.5 Workload Manager–specific constants and config

| Name | Value / type | Location |
|------|----------------|----------|
| `DefaultSandboxTTL` | `8 * time.Hour` | `k8s_client.go` |
| `DefaultSandboxIdleTimeout` | `15 * time.Minute` | `k8s_client.go` |
| `SessionIdLabelKey` | `runtime.agentcube.io/session-id` | `k8s_client.go` |
| `WorkloadNameLabelKey` | `runtime.agentcube.io/workload-name` | `k8s_client.go` |
| `SandboxNameLabelKey` | `runtime.agentcube.io/sandbox-name` | `k8s_client.go` |
| `LastActivityAnnotationKey` | `last-activity-time` | `k8s_client.go` |
| `IdleTimeoutAnnotationKey` | `runtime.agentcube.io/idle-timeout` | `k8s_client.go` |
| `IdentitySecretName` | `picod-router-identity` | `workload_builder.go` |
| `PublicKeyDataKey` | `public.pem` | `workload_builder.go` |
| `IdentitySecretNamespace` | `default`, overridden by `AGENTCUBE_NAMESPACE` | `workload_builder.go` |
| `gcOnceTimeout` | `2 * time.Minute` | `garbage_collection.go` |
| GC ticker interval | `15 * time.Second` (passed to `newGarbageCollector` from `server.Start`) | `server.go` |
| GC batch `limit` | `16` per list call (inactive + expired) | `garbage_collection.go` |
| Sandbox create wait | `2 * time.Minute` select timeout | `handlers.go` |
| User client cache size | `100` | `NewK8sClient` |
| REST `QPS` / `Burst` | `50` / `100` | `NewK8sClient` |

**`workloadmanager.Config` struct fields**

| Field | Go type | Used in code |
|-------|---------|----------------|
| `Port` | `string` | listen |
| `RuntimeClassName` | `string` | **Not referenced** after `main` passes it (dead field in current implementation) |
| `EnableTLS` | `bool` | TLS listen |
| `TLSCert` / `TLSKey` | `string` | TLS paths |
| `EnableAuth` | `bool` | middleware + user dynamic client |

### 6.6 GVR helpers (`informers.go`)

| Variable | GVR |
|----------|-----|
| `AgentRuntimeGVR` | `runtime.agentcube.volcano.sh/v1alpha1`, resource `agentruntimes` |
| `CodeInterpreterGVR` | `runtime.agentcube.volcano.sh/v1alpha1`, resource `codeinterpreters` |
| `SandboxGVR` | `agents.x-k8s.io/v1alpha1`, resource `sandboxes` |
| `SandboxClaimGVR` | `extensions.agents.x-k8s.io/v1alpha1`, resource `sandboxclaims` |

### 6.7 Garbage collection

**Trigger:** ticker every **15s** after server start.

**Per tick (`once`):**

1. Context timeout **2 minutes**.
2. **Inactive:** `ListInactiveSandboxes(ctx, time.Now().Add(-DefaultSandboxIdleTimeout), 16)` — i.e. last activity **before** now−15m.
3. **Expired:** `ListExpiredSandboxes(ctx, time.Now(), 16)` — expiry index score ≤ now.
4. Union lists; for each: delete Sandbox or SandboxClaim via cluster `dynamicClient`; on success `DeleteSandboxBySessionID`; aggregate errors logged.

**Note:** GC uses the **cluster** `k8sClient.dynamicClient`, not the per-user client.

### 6.8 `SandboxReconciler` (agent-sandbox `Sandbox`)

- **Watches:** `sandboxv1alpha1.Sandbox` — registered in `cmd/workload-manager` via `setupControllers` using the **same** `SandboxReconciler` pointer passed to `NewServer` for `WatchSandboxOnce` / `UnWatchSandbox`.
- **Trigger:** any reconcile request for a Sandbox.
- **Logic:** Load Sandbox; `getSandboxStatus` returns `"running"` if condition type `SandboxConditionReady` (from agent-sandbox API) is `True`; then non-blocking send on registered waiter channel for that namespaced name; removes waiter entry before send.
- **Status writes:** none in this reconciler.

### 6.9 `CodeInterpreterReconciler`

- **Watches:** `runtimev1alpha1.CodeInterpreter`.
- **Warm pool:** If `WarmPoolSize != nil && *WarmPoolSize > 0`: ensure `SandboxTemplate` (name = CI name), ensure `SandboxWarmPool` (name = CI name, template ref = CI name); else delete warm pool then template.
- **Public key gate:** If `AuthMode != AuthModeNone` and public key not cached → `RequeueAfter: 5s` before creating template.
- **Pod env:** Injects `PICOD_AUTH_PUBLIC_KEY` from cached Router secret when auth mode is not `none`.
- **Status:** Sets `Status.Ready = true` and upserts `Condition` type `Ready`, status `True`, reason `Reconciled`, message `CodeInterpreter is ready`, `ObservedGeneration` = `ci.Generation`; `Status().Update`.

### 6.10 Sandbox build highlights

- **AgentRuntime:** Sandbox name `{name}-{8 random alnum}`; labels `managed-by=agentcube-workload-manager`; idle timeout in annotation `runtime.agentcube.io/idle-timeout`; TTL from `MaxSessionDuration` or default 8h; shutdown time on Sandbox lifecycle.
- **CodeInterpreter:** Same naming; if warm pool: `SandboxClaim` + minimal Sandbox metadata, `Kind` in store path `SandboxClaim`; else full Pod from template. Default ports if empty: single `TargetPort` port `8080`, protocol `HTTP`, path `/`.
- **Public key:** Background load from Secret `picod-router-identity` / key `public.pem` in `IdentitySecretNamespace`, exponential backoff 100ms–10s.

---

## 7. Router (`pkg/router`)

### 7.1 `router.Config`

| Field | Go type | Default in `NewServer` |
|-------|---------|-------------------------|
| `Port` | `string` | from CLI |
| `Debug` | `bool` | — |
| `EnableTLS` | `bool` | — |
| `TLSCert` / `TLSKey` | `string` | — |
| `MaxConcurrentRequests` | `int` | if `<= 0` → **1000** |

**Unused in routing logic:** `router.LastActivityAnnotationKey` = `agentcube.volcano.sh/last-activity` (differs from workload manager’s `last-activity-time`; agentd uses workload manager’s key).

### 7.2 Routes

| Method | Path | Auth | Notes |
|--------|------|------|--------|
| `GET` | `/health/live` | None | `{"status":"alive"}` |
| `GET` | `/health/ready` | None | 200 `{"status":"ready"}` or 503 if session manager nil |
| `GET` | `/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path` | None | Proxy |
| `POST` | `/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path` | None | Proxy |
| `GET` | `/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path` | None | Proxy |
| `POST` | `/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path` | None | Proxy |

**`/v1` middleware:** `gin.Logger()`, `gin.Recovery()`, `concurrencyLimitMiddleware` (semaphore; if full → **429** with `{"error":"...","code":"SERVER_OVERLOADED"}`).

### 7.3 Session and upstream behavior

- **Header (client → router):** `x-agentcube-session-id` — empty triggers new sandbox via Workload Manager.
- **Env (router):** `WORKLOAD_MANAGER_URL` **required** for `NewSessionManager`; POST to `/v1/agent-runtime` or `/v1/code-interpreter` with `CreateSandboxRequest` JSON; optional `Authorization: Bearer <token>` from service account token file `/var/run/secrets/kubernetes.io/serviceaccount/token` if readable.
- **Store:** `UpdateSessionLastActivity` called before and after proxy (best-effort, warnings on failure).
- **Upstream selection:** Longest-prefix match on `SandboxEntryPoint.Path`; else first entry; URL built with `protocol://endpoint` if endpoint has no scheme.
- **Downstream auth:** For `Sandbox` or `SandboxClaim` kinds, sets `Authorization: Bearer <jwt>` on proxied request.
- **Response header:** `x-agentcube-session-id` set on proxied response.

### 7.4 JWT (`jwt.go`)

| Item | Value |
|------|--------|
| **Algorithm** | RS256 (`jwt.SigningMethodRS256`) |
| **Key type** | RSA 2048-bit (`rsa.GenerateKey`, `rsaKeySize = 2048`) |
| **Private key PEM** | PKCS1 (`RSA PRIVATE KEY`) |
| **Public key PEM** | PKIX (`PUBLIC KEY`) |
| **Standard claims** | `exp` = now + **5 minutes**; `iat` = now; `iss` = **`agentcube-router`** |
| **Audience (`aud`)** | **Not set** |
| **Custom claims** | `session_id` (sandbox session UUID) |
| **Verification options (PicoD)** | `WithExpirationRequired`, `WithIssuedAt`, `WithLeeway(time.Minute)` |

**Secret:** `picod-router-identity` in namespace from `AGENTCUBE_NAMESPACE` or `default`; data keys `private.pem`, `public.pem`. Create on startup if missing; if already exists load private key and replace in-memory pair. If not in cluster (`InClusterConfig` fails), keys stay ephemeral (warning logged). *Comment in source mentions ConfigMap; implementation stores both keys in the Secret only.*

### 7.5 Server timeouts

- `ReadTimeout` **30s**, `IdleTimeout` **90s**; graceful shutdown on context cancel with **10s** timeout.

---

## 8. PicoD (`pkg/picod`)

### 8.1 `Config`

| Field | Go type | JSON tag (struct only; not used for HTTP) |
|-------|---------|--------------------------------------------|
| `Port` | `int` | `json:"port"` |
| `Workspace` | `string` | `json:"workspace"` |

### 8.2 Routes

| Method | Path | Auth |
|--------|------|------|
| `GET` | `/health` | None |
| `POST` | `/api/execute` | JWT middleware |
| `POST` | `/api/files` | JWT middleware |
| `GET` | `/api/files` | JWT middleware |
| `GET` | `/api/files/*path` | JWT middleware |

### 8.3 Auth (`auth.go`)

| Constant | Value |
|----------|--------|
| `MaxBodySize` | `32 << 20` (32 MiB) |
| `PublicKeyEnvVar` | `PICOD_AUTH_PUBLIC_KEY` |

- Middleware: Bearer JWT, RSA signature check, `jwt.SigningMethodRSA`, leeway **1 minute**, expiration required.
- On authenticated routes, wraps `Request.Body` with `http.MaxBytesReader(..., MaxBodySize)`.

### 8.4 `/api/execute`

**Request `ExecuteRequest`**

| Field | Go type | JSON tag |
|-------|---------|----------|
| `Command` | `[]string` | `json:"command"` (required) |
| `Timeout` | `string` | `json:"timeout"` |
| `WorkingDir` | `string` | `json:"working_dir"` |
| `Env` | `map[string]string` | `json:"env"` |

- Default execution timeout if `Timeout` empty: **60 seconds** (implementation; struct comment mentions 30s — code uses 60s).
- Response `ExecuteResponse`: `stdout`, `stderr`, `exit_code`, `duration`, `start_time`, `end_time` with JSON tags `stdout`, `stderr`, `exit_code`, `duration`, `start_time`, `end_time`.
- `TimeoutExitCode` = **124** on context deadline.

### 8.5 `/api/files`

- **POST JSON** `UploadFileRequest`: `path`, `content` (base64), optional `mode` (octal string).
- **POST multipart:** form fields `path`, file field `file`, optional `mode`.
- **GET list:** query `path` required → `ListFilesResponse` `{ "files": [ FileEntry ... ] }` with entries `name`, `size`, `modified`, `mode`, `is_dir`.
- **GET download:** path param; sends file with attachment headers.

### 8.6 `/health`

JSON: `status`, `service` (`PicoD`), `version` (`0.0.1`), `uptime` (string duration since server start).

### 8.7 Server

- `ReadHeaderTimeout` **10s**.

---

## 9. Agentd (`pkg/agentd`)

| Name | Value |
|------|--------|
| `SessionExpirationTimeout` | `15 * time.Minute` (package var) |

**Reconciler:** watches `sandboxv1alpha1.Sandbox`.

- Reads annotation **`last-activity-time`** (`workloadmanager.LastActivityAnnotationKey`) as RFC3339.
- If parsed and `now.After(lastActivity + SessionExpirationTimeout)` → `Delete` Sandbox.
- Else if annotation present → `RequeueAfter` until expiration.
- If annotation missing / empty → no deletion, finish.

---

## 10. Command-line entrypoints (`cmd/`)

All binaries that call `klog.InitFlags(nil)` also expose **standard klog flags** (verbosity, logging destinations, etc.); see `k8s.io/klog/v2`.

### 10.1 `workload-manager`

| Flag | Default | Description |
|------|---------|-------------|
| `-port` | `8080` | API server port |
| `-runtime-class-name` | `kuasar-vmm` | Passed into `Config` but unused in current pkg code |
| `-enable-tls` | `false` | HTTPS |
| `-tls-cert` | `""` | Cert path |
| `-tls-key` | `""` | Key path |
| `-enable-auth` | `false` | Service-account TokenReview auth |

### 10.2 `router`

| Flag | Default | Description |
|------|---------|-------------|
| `-port` | `8080` | Router listen port |
| `-enable-tls` | `false` | HTTPS |
| `-tls-cert` | `""` | Cert path |
| `-tls-key` | `""` | Key path |
| `-debug` | `false` | Gin debug mode |
| `-max-concurrent-requests` | `1000` | 0 = unlimited in `Config`; `NewServer` replaces `<=0` with 1000 |

### 10.3 `picod`

| Flag | Default | Description |
|------|---------|-------------|
| `-port` | `8080` | Listen port |
| `-workspace` | `""` | Workspace root; empty → current working directory |

### 10.4 `agentd`

- **No CLI flags** in `main`; controller-runtime manager from in-cluster/kubeconfig via `ctrl.GetConfigOrDie()`, metrics and health probes disabled (`BindAddress: "0"`).

---

## 11. client-go (generated)

**Module path prefix:** `github.com/volcano-sh/agentcube/client-go/...`

### 11.1 Layout

- `clientset/versioned` — typed clientset
- `clientset/versioned/typed/runtime/v1alpha1` — group client + resource interfaces
- `informers/externalversions` — shared informer factory
- `listers/runtime/v1alpha1` — listers

### 11.2 Core interfaces

**`versioned.Interface`**

```go
type Interface interface {
    Discovery() discovery.DiscoveryInterface
    RuntimeV1alpha1() runtimev1alpha1.RuntimeV1alpha1Interface
}
```

**`runtimev1alpha1.RuntimeV1alpha1Interface`**

```go
type RuntimeV1alpha1Interface interface {
    RESTClient() rest.Interface
    AgentRuntimesGetter
    CodeInterpretersGetter
}
```

**`runtimev1alpha1.AgentRuntimeInterface`** — CRUD + `UpdateStatus`, `Watch`, `Patch`, etc. on `*runtimev1alpha1.AgentRuntime` / `AgentRuntimeList`; REST resource name **`agentruntimes`**.

**`runtimev1alpha1.CodeInterpreterInterface`** — same pattern for `*runtimev1alpha1.CodeInterpreter` / `CodeInterpreterList`; REST resource name **`codeinterpreters`**.

**Factory:** `informers/externalversions.NewSharedInformerFactory(client versioned.Interface, defaultResync time.Duration)` and variants (namespace-scoped, tweak list options, custom resync).

---

## 12. Environment variable summary

| Variable | Component | Purpose |
|----------|-----------|---------|
| `AGENTCUBE_NAMESPACE` | Router JWT secret, WM identity secret namespace | Override default `default` |
| `WORKLOAD_MANAGER_URL` | Router session manager | Base URL for WM API (required) |
| `STORE_TYPE` | Store | `redis` (default) or `valkey` |
| `REDIS_ADDR`, `REDIS_PASSWORD`, `REDIS_PASSWORD_REQUIRED` | Redis store | Connection + password policy |
| `VALKEY_ADDR`, `VALKEY_PASSWORD`, `VALKEY_PASSWORD_REQUIRED`, `VALKEY_DISABLE_CACHE`, `VALKEY_FORCE_SINGLE` | Valkey store | Connection + client options |
| `PICOD_AUTH_PUBLIC_KEY` | PicoD | PEM public key for JWT verification |

---

## 13. Cross-reference: agent-sandbox CRDs (external)

The workload manager and agentd depend on **sigs.k8s.io/agent-sandbox** types (e.g. `Sandbox`, `SandboxClaim`, `SandboxTemplate`, `SandboxWarmPool`, annotations such as `agents.x-k8s.io/sandbox-pod-name`). Their full OpenAPI is defined in that module, not duplicated here.

---

*End of specification.*
