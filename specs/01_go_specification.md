# AgentCube Go Source Specification

> Reverse-engineered from https://github.com/ShijunDeng/agentcube.git
> Generated at: 2026-03-21T03:09:00Z (Stage 1 of SDD Benchmark)

---

## 1. Module and Layout

Module: `github.com/volcano-sh/agentcube`, Go 1.24.x

| Area | Role |
|------|------|
| `cmd/` | Binaries: `workload-manager`, `router`, `agentd`, `picod` |
| `pkg/apis/runtime/v1alpha1` | CRD Go types (`AgentRuntime`, `CodeInterpreter`) |
| `pkg/workloadmanager` | HTTP API + Sandbox/CodeInterpreter reconciliation + K8s + GC |
| `pkg/router` | Edge HTTP proxy, sessions, JWT to sandboxes |
| `pkg/store` | Redis/Valkey session store |
| `pkg/common/types` | Shared DTOs |
| `pkg/api` | API errors helpers |
| `pkg/agentd` | Optional Sandbox idle cleanup controller |
| `pkg/picod` | In-sandbox daemon (execute + files) |
| `client-go/` | Generated typed client, informers, listers |

## 2. CRDs (`runtime.agentcube.volcano.sh/v1alpha1`)

### 2.1 AgentRuntime

**AgentRuntimeSpec:**
- `targetPort` ([]TargetPort): Exposed ports
- `podTemplate` (*SandboxTemplate): Required, contains PodSpec
- `sessionTimeout` (*metav1.Duration): Default 15m
- `maxSessionDuration` (*metav1.Duration): Default 8h

**AgentRuntimeStatus:** `conditions []metav1.Condition`

**SandboxTemplate:** `labels`, `annotations` (map[string]string), `spec` (corev1.PodSpec)

### 2.2 CodeInterpreter

**CodeInterpreterSpec:**
- `ports` ([]TargetPort): Optional
- `template` (*CodeInterpreterSandboxTemplate): Required
- `sessionTimeout` (*metav1.Duration): Default 15m
- `maxSessionDuration` (*metav1.Duration): Default 8h
- `warmPoolSize` (*int32)
- `authMode` (AuthModeType): `picod` | `none`, default `picod`

**CodeInterpreterSandboxTemplate:** labels, annotations, runtimeClassName, image, imagePullPolicy, imagePullSecrets, environment, command, args, resources

**CodeInterpreterStatus:** `conditions []metav1.Condition`, `ready bool`

### 2.3 Shared Types

**TargetPort:** `pathPrefix`, `name`, `port` (uint32), `protocol` (`HTTP`|`HTTPS`)

**Constants:** `AuthModePicoD="picod"`, `AuthModeNone="none"`, `ProtocolTypeHTTP`, `ProtocolTypeHTTPS`

## 3. Workload Manager HTTP API

**Server:** Gin + h2c HTTP/2, optional TLS

| Method | Path | Auth | Handler |
|--------|------|------|---------|
| GET | `/health` | No | handleHealth |
| POST | `/v1/agent-runtime` | If enabled | handleAgentRuntimeCreate |
| DELETE | `/v1/agent-runtime/sessions/:sessionId` | If enabled | handleDeleteSandbox |
| POST | `/v1/code-interpreter` | If enabled | handleCodeInterpreterCreate |
| DELETE | `/v1/code-interpreter/sessions/:sessionId` | If enabled | handleDeleteSandbox |

**Create Flow:** Bind JSON → CreateSandboxRequest → build Sandbox → WatchSandboxOnce → K8s create → wait 2m for running → resolve pod IP → return response

**Auth:** Bearer SA token → K8s TokenReview

**GC:** Every 15s, batch 16, ListInactiveSandboxes + ListExpiredSandboxes → delete

## 4. Router HTTP API

| Method | Path |
|--------|------|
| GET | `/health/live`, `/health/ready` |
| GET/POST | `/v1/namespaces/:namespace/agent-runtimes/:name/invocations/*path` |
| GET/POST | `/v1/namespaces/:namespace/code-interpreters/:name/invocations/*path` |

**Invoke Flow:** Session lookup/create → determine upstream URL → reverse proxy + JWT Authorization header → update last activity

**JWT:** RSA 2048, RS256, 5m exp, iss "agentcube-router", secret "picod-router-identity"

## 5. Store Interface

`Ping`, `GetSandboxBySessionID`, `StoreSandbox`, `UpdateSandbox`, `DeleteSandboxBySessionID`, `ListExpiredSandboxes`, `ListInactiveSandboxes`, `UpdateSessionLastActivity`, `Close`

Implementations: Redis (default), Valkey. Keys: `session:{id}`, ZSET `session:expiry`, `session:last_activity`

## 6. PicoD (In-Sandbox Daemon)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/execute` | Run command (60s timeout) |
| POST | `/api/files` | Upload files |
| GET | `/api/files` | List directory |
| GET | `/api/files/*path` | Download file |
| GET | `/health` | Health check |

JWT middleware on `/api/*`, RS256 with PICOD_AUTH_PUBLIC_KEY

## 7. Agentd

Reconciler on Sandbox: reads `last-activity-time` annotation, deletes if idle > 15m, else requeue

## 8. CLI Binaries (Flags)

| Binary | Flags |
|--------|-------|
| workload-manager | -port, -runtime-class-name (kuasar-vmm), -enable-tls, -tls-cert, -tls-key, -enable-auth |
| router | -port, -enable-tls, -tls-cert, -tls-key, -debug, -max-concurrent-requests |
| agentd | (controller-runtime manager only) |
| picod | -port (8080), -workspace |
