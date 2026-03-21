# Session Routing — Design

## Module

- Same repository: `github.com/volcano-sh/agentcube` (see sandbox-orchestration design for `go.mod` and versions).

## Package `github.com/volcano-sh/agentcube/pkg/router`

### Config

```go
const LastActivityAnnotationKey = "agentcube.volcano.sh/last-activity"

type Config struct {
    Port                  string
    Debug                 bool
    EnableTLS             bool
    TLSCert               string
    TLSKey                string
    MaxConcurrentRequests int  // 0 = unlimited at flag level; NewServer coerces to 1000
}
```

### CLI flags (`cmd/router/main.go`)

| Flag | Default |
|------|---------|
| `-port` | `8080` |
| `-enable-tls` | `false` |
| `-tls-cert` | `""` |
| `-tls-key` | `""` |
| `-debug` | `false` |
| `-max-concurrent-requests` | `1000` (0 means unlimited per flag help; `NewServer` still sets default 1000 when `<= 0`) |

### Server struct

```go
type Server struct {
    config         *Config
    engine         *gin.Engine
    httpServer     *http.Server
    sessionManager SessionManager
    storeClient    store.Store
    httpTransport  *http.Transport
    jwtManager     *JWTManager
}
```

- `httpTransport`: `IdleConnTimeout: 0`, `DisableCompression: false`.
- Store: `store.Storage()` for both session manager and `storeClient`.
- Gin mode: `DebugMode` if `config.Debug`, else `ReleaseMode`.

### Route table

| Method | Path | Middleware | Handler |
|--------|------|------------|---------|
| GET | `/health/live` | none | `handleHealthLive` |
| GET | `/health/ready` | none | `handleHealthReady` |
| GET | `/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path` | `gin.Logger`, `gin.Recovery`, `concurrencyLimitMiddleware` | `handleAgentInvoke` |
| POST | same | same | `handleAgentInvoke` |
| GET | `/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path` | same | `handleCodeInterpreterInvoke` |
| POST | same | same | `handleCodeInterpreterInvoke` |

### SessionManager interface

```go
type SessionManager interface {
    GetSandboxBySession(ctx context.Context, sessionID string, namespace string, name string, kind string) (*types.SandboxInfo, error)
}
```

### manager implementation (`session_manager.go`)

```go
type manager struct {
    storeClient     store.Store
    workloadMgrAddr string
    httpClient      *http.Client
}
```

- `NewSessionManager(storeClient store.Store) (SessionManager, error)` reads `WORKLOAD_MANAGER_URL` (required).
- HTTP client: `Timeout: 2 * time.Minute`; transport `MaxIdleConnsPerHost: 100`, `DisableCompression: false`; `http2.ConfigureTransports` with `ReadIdleTimeout: 30s`, `PingTimeout: 15s`.
- Endpoints: `AgentRuntime` → `{WORKLOAD_MANAGER_URL}/v1/agent-runtime`; `CodeInterpreter` → `.../v1/code-interpreter`.
- Request: `Content-Type: application/json`; optional `Authorization: Bearer` from `loadWorkloadManagerAuthToken()` reading `/var/run/secrets/kubernetes.io/serviceaccount/token` (trimmed); missing file → no header (warning if non-NotExist error).

### JWT (`jwt.go`)

**Constants (unexported unless noted):**

| Name | Value |
|------|--------|
| `rsaKeySize` | `2048` |
| `jwtExpiration` | `5 * time.Minute` |
| `IdentitySecretName` | `"picod-router-identity"` |
| `PrivateKeyDataKey` | `"private.pem"` |
| `PublicKeyDataKey` | `"public.pem"` |

```go
var IdentityNamespace = "default" // init: AGENTCUBE_NAMESPACE if set
```

**JWTManager:**

```go
type JWTManager struct {
    privateKey *rsa.PrivateKey
    publicKey  *rsa.PublicKey
    clientset  kubernetes.Interface
}
```

- `NewJWTManager()`: `rsa.GenerateKey(rand.Reader, rsaKeySize)`.
- `GenerateToken(claims map[string]interface{}) (string, error)`:
  - Base claims: `exp` = now+jwtExpiration (Unix), `iat` = now (Unix), `iss` = `"agentcube-router"`.
  - Merges custom claims (e.g. `session_id`).
  - Signing: `jwt.SigningMethodRS256`, signed with RSA private key.

**Algorithm:** RS256  
**Key type:** RSA 2048-bit, PKCS1 private key PEM (`RSA PRIVATE KEY`), PKIX public key PEM (`PUBLIC KEY`).

**TryStoreOrLoadJWTKeySecret(ctx):**

- If `clientset == nil`, try `rest.InClusterConfig()`; on failure log warning and return nil (ephemeral keys).
- Else build Secret `IdentitySecretName` in `IdentityNamespace`, type `Opaque`, labels `app=agentcube`, `component=router`, data `private.pem` + `public.pem`.
- Create; on `AlreadyExists`, Get secret and `loadPrivateKeyPEM`.

### Reverse proxy

- `httputil.NewSingleHostReverseProxy(targetURL)`; `proxy.Transport = s.httpTransport`.
- Director: sets `req.URL.Path` to normalized path, clears `RawPath`, `req.Host = targetURL.Host`, forwarding headers, `Authorization` if JWT non-empty.
- `ModifyResponse`: sets `x-agentcube-session-id`.
- No per-request timeout wrapper (commented-out context timeout in source).

### Concurrency middleware

- Buffered channel size `config.MaxConcurrentRequests`.
- `select`: send to channel or `default` → 429 + abort.

### Health JSON shapes

- Live: `{"status":"alive"}`.
- Ready OK: `{"status":"ready"}`.
- Ready fail: `{"status":"not ready","error":"session manager not available"}`.

### Error helper (`handleGetSandboxError`)

- If `apierrors.APIStatus`: use `Status().Code` if non-zero; message from status or `err.Error()`; if code is 500, replace message with `internal server error`; respond `gin.H{"error": message}`.
- Else 500 `{"error":"internal server error"}`.

### Environment variables

| Variable | Used by |
|----------|---------|
| `WORKLOAD_MANAGER_URL` | Session manager (required) |
| `AGENTCUBE_NAMESPACE` | JWT secret namespace (optional, default `default`) |

### Dependencies (direct use in router)

- `github.com/gin-gonic/gin`, `github.com/golang-jwt/jwt/v5`, `golang.org/x/net/http2`, `k8s.io/api`, `k8s.io/apimachinery`, `k8s.io/client-go`, `k8s.io/klog/v2`, `github.com/volcano-sh/agentcube/pkg/store`, `github.com/volcano-sh/agentcube/pkg/common/types`, `github.com/volcano-sh/agentcube/pkg/api`.
