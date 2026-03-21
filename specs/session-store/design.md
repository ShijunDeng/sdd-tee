# Session Store — Design

## Module

- `github.com/volcano-sh/agentcube` — versions in sandbox-orchestration `design.md`.

## Package `github.com/volcano-sh/agentcube/pkg/store`

### Store interface (exact signatures)

```go
package store

import (
    "context"
    "time"

    "github.com/volcano-sh/agentcube/pkg/common/types"
)

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

### Errors

```go
var ErrNotFound = errors.New("store: not found")
```

### Provider type constants (`singleton.go`)

```go
const (
    redisStoreType  string = "redis"
    valkeyStoreType string = "valkey"
)
```

### Singleton

```go
var (
    initStoreOnce = &sync.Once{}
    provider      Store
)

func Storage() Store
func initStore() error
```

- `Storage()` calls `initStoreOnce.Do(initStore)`; on error `klog.Fatalf("init store failed: %v", err)`.

### Sandbox document type

Stored JSON unmarshals to `github.com/volcano-sh/agentcube/pkg/common/types.SandboxInfo`:

```go
type SandboxInfo struct {
    Kind             string              `json:"kind"`
    SandboxID        string              `json:"sandboxId"`
    SandboxNamespace string              `json:"sandboxNamespace"`
    Name             string              `json:"name"`
    EntryPoints      []SandboxEntryPoint `json:"entryPoints"`
    SessionID        string              `json:"sessionId"`
    CreatedAt        time.Time           `json:"createdAt"`
    ExpiresAt        time.Time           `json:"expiresAt"`
    Status           string              `json:"status"`
}

type SandboxEntryPoint struct {
    Path     string `json:"path"`
    Protocol string `json:"protocol"`
    Endpoint string `json:"endpoint"`
}
```

## Redis implementation (`store_redis.go`)

### Struct

```go
type redisStore struct {
    cli                  *redisv9.Client  // github.com/redis/go-redis/v9
    sessionPrefix        string
    expiryIndexKey       string
    lastActivityIndexKey string
}
```

### Fixed key patterns

| Field | Value |
|-------|--------|
| `sessionPrefix` | `"session:"` |
| `expiryIndexKey` | `"session:expiry"` |
| `lastActivityIndexKey` | `"session:last_activity"` |

### Connection options (`makeRedisOptions`)

```go
return &redisv9.Options{
    Addr:     redisAddr,     // REDIS_ADDR
    Password: redisPassword, // REDIS_PASSWORD
}, nil
```

### Environment variables (Redis)

| Variable | Required | Notes |
|----------|----------|--------|
| `REDIS_ADDR` | Yes | |
| `REDIS_PASSWORD` | Yes unless `REDIS_PASSWORD_REQUIRED=false` | Case-insensitive compare to `"false"` |
| `STORE_TYPE` | No | Default `redis` |

### Operations summary

| Method | Redis commands |
|--------|----------------|
| `Ping` | `PING` → expect `PONG` |
| `GetSandboxBySessionID` | `GET session:{id}` |
| `StoreSandbox` | Pipeline: `SETNX`, `ZADD session:expiry`, `ZADD session:last_activity` |
| `UpdateSandbox` | `SET key value XX` |
| `DeleteSandboxBySessionID` | Pipeline: `DEL`, `ZREM expiry`, `ZREM last_activity` |
| `ListExpiredSandboxes` | `ZRANGEBYSCORE session:expiry -inf {before.Unix} LIMIT 0 limit` then pipeline GETs |
| `ListInactiveSandboxes` | `ZRANGEBYSCORE session:last_activity ...` then pipeline GETs |
| `UpdateSessionLastActivity` | `GET` (existence), then `ZADD session:last_activity` |
| `Close` | `cli.Close()` |

- `List*` with `limit <= 0` returns `nil, nil`.
- `sessionKey(id)` → `sessionPrefix + sessionID`.

## Valkey implementation (`store_valkey.go`)

### Struct

```go
type valkeyStore struct {
    cli                  valkey.Client  // github.com/valkey-io/valkey-go
    sessionPrefix        string
    expiryIndexKey       string
    lastActivityIndexKey string
}
```

Same string constants as Redis for prefix and ZSET keys.

### Connection options (`makeValkeyOptions`)

```go
valkeyClientOptions := &valkey.ClientOption{
    InitAddress: strings.Split(valkeyAddr, ","),
    Password:    valkeyPassword,
}
```

Optional: `DisableCache` from `VALKEY_DISABLE_CACHE` (ParseBool, must be true); `ForceSingleClient` from `VALKEY_FORCE_SINGLE` (ParseBool, must be true).

### Environment variables (Valkey)

| Variable | Required | Notes |
|----------|----------|--------|
| `VALKEY_ADDR` | Yes | Comma-separated list → `InitAddress` |
| `VALKEY_PASSWORD` | Yes unless `VALKEY_PASSWORD_REQUIRED=false` | |
| `VALKEY_DISABLE_CACHE` | No | `"true"` enables `DisableCache` |
| `VALKEY_FORCE_SINGLE` | No | `"true"` enables `ForceSingleClient` |
| `STORE_TYPE` | Must be `valkey` | Case-insensitive |

### Operations summary

| Method | Valkey API |
|--------|------------|
| `Ping` | `B().Ping()` → string `PONG` |
| `GetSandboxBySessionID` | `B().Get().Key(key)` → bytes; `IsValkeyNil` → `ErrNotFound` |
| `StoreSandbox` | `DoMulti`: `SETNX`, `ZADD` expiry, `ZADD` last_activity |
| `UpdateSandbox` | `SET ... XX`; success requires `ToString() == "OK"` |
| `DeleteSandboxBySessionID` | `DoMulti`: `DEL`, `ZREM` expiry, `ZREM` last_activity |
| `ListExpiredSandboxes` | `Zrangebyscore` with `Min("-inf")`, `Max(fmt.Sprintf("%d", before.Unix()))`, `Limit(0, limit)` |
| `ListInactiveSandboxes` | Same on `last_activity` key |
| `UpdateSessionLastActivity` | `Exists` key → int64 must be 1; then `Zadd` |
| `Close` | `vs.cli.Close()` then return nil |

### ZSET score semantics

- **Expiry index:** score = `float64(sandboxRedis.ExpiresAt.Unix())` on store.
- **Last activity:** score = `float64(time.Now().Unix())` on `StoreSandbox`; `float64(at.Unix())` on `UpdateSessionLastActivity`.

### MGET note (Valkey)

- `loadSandboxesBySessionIDs` builds all `session:{id}` keys and uses single `Mget`; comment states keys should be in same slot (deployment consideration).

## Dependencies (store package imports)

- `github.com/redis/go-redis/v9`
- `github.com/valkey-io/valkey-go`
- `k8s.io/klog/v2` (Valkey options logging)
- `github.com/volcano-sh/agentcube/pkg/common/types`
