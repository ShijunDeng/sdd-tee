# AR-005 — Sandbox 创建处理器 Design

## Overview

| Item | Value |
|------|-------|
| AR | AR-005 — Sandbox 创建处理器 |
| Module | `pkg/workloadmanager` |
| Language | Go |
| Size | M |
| Stage | ST-1 completed |

Sandbox 创建处理器负责处理 `POST /v1/agent-runtime` 和 `POST /v1/code-interpreter` 请求，将用户的 AgentRuntime 或 CodeInterpreter 定义转化为实际的 Sandbox（或 SandboxClaim）Kubernetes 资源，等待其进入 running 状态，解析 Pod IP 和入口点，持久化到 Store，并返回包含 sessionId 的响应。

## Architecture

### 组件交互

```
Client
  → POST /v1/agent-runtime 或 POST /v1/code-interpreter
    → authMiddleware（可选，EnableAuth=true 时生效）
      → handleAgentRuntimeCreate / handleCodeInterpreterCreate
        → 1. 解析并验证 CreateSandboxRequest
        → 2. 从 Informer 缓存获取 AgentRuntime/CodeInterpreter
        → 3. 构建 Sandbox/SandboxClaim 对象（workload_builder）
        → 4. StoreSandbox 占位记录
        → 5. WatchSandboxOnce 注册一次性 watcher
        → 6. 通过 dynamic client 创建 CR
        → 7. 等待 SandboxReconciler 通知 running（最长 2 分钟）
        → 8. 解析 Pod IP 和 entryPoints
        → 9. UpdateSandbox 更新完整信息
        → 10. 返回 CreateSandboxResponse
```

### 关键依赖

- **client-go typed client**: `github.com/volcano-sh/agentcube/client-go` 提供 `AgentRuntimeInterface` 和 `CodeInterpreterInterface`，用于读取 workload 模板定义
- **client-go informers**: `SharedInformerFactory` → `Runtime().V1alpha1().AgentRuntimes()` / `CodeInterpreters()` 提供本地缓存
- **client-go listers**: `AgentRuntimeLister` / `CodeInterpreterLister` 用于只读查询
- **dynamic client**: 创建外部 CRD（Sandbox/SandboxClaim，来自 `sigs.k8s.io/agent-sandbox`）
- **SandboxReconciler**: controller-runtime reconciler，监听 Sandbox 状态变化并通过 channel 通知等待方
- **Store**: Redis 持久化层，存储 SandboxInfo 占位和最终记录

### 数据流

```
CreateSandboxRequest (JSON)
  → Validate()
  → Informer Lister.Get(namespace, name)
    → AgentRuntime / CodeInterpreter
      → buildSandboxObject() / buildSandboxClaimObject()
        → unstructured.Unstructured
          → dynamicClient.Resource(GVR).Namespace(ns).Create()
            → SandboxReconciler.WaitSandboxOnce(ns, name) → chan
              ← Sandbox status = running
                → resolvePodIP()
                  → UpdateSandbox(full SandboxInfo)
                    → CreateSandboxResponse (JSON 200)
```

## Data Structures

### 请求/响应模型

已在 `pkg/common/types` 定义，处理器直接引用：

```go
// 请求体 — 由客户端传入
type CreateSandboxRequest struct {
    Kind      string `json:"kind"`      // "AgentRuntime" 或 "CodeInterpreter"
    Name      string `json:"name"`      // workload 名称
    Namespace string `json:"namespace"` // workload 所在 namespace
}

// Validate 校验规则:
// - Kind 必须为 AgentRuntime 或 CodeInterpreter
// - Namespace 非空
// - Name 非空
// 任一失败返回 fmt.Errorf("%s is required", field)

// 响应体 — 成功时返回
type CreateSandboxResponse struct {
    SessionID   string              `json:"sessionId"`
    SandboxID   string              `json:"sandboxId"`
    SandboxName string              `json:"sandboxName"`
    EntryPoints []SandboxEntryPoint `json:"entryPoints"`
}

type SandboxEntryPoint struct {
    Path     string `json:"path"`     // 路由路径前缀
    Protocol string `json:"protocol"` // "HTTP" 或 "HTTPS"
    Endpoint string `json:"endpoint"` // "host:port"
}
```

### 处理器内部结构

```go
// sandboxCreator 封装创建逻辑的所有依赖
type sandboxCreator struct {
    k8sClient         *K8sClient           // dynamic client + informer factory
    sandboxController *SandboxReconciler   // 等待 sandbox running
    storeClient       store.Store          // Redis 持久化
    publicKey         []byte               // PicoD 公钥（authMode=picod 时注入）
}
```

### 上下文传递

创建过程中通过 `context.Context` 传递：

| Key | Type | 来源 |
|-----|------|------|
| `contextKeyUserToken` | `string` | authMiddleware（auth 启用时） |
| `contextKeyServiceAccount` | `string` | authMiddleware |
| `contextKeyServiceAccountName` | `string` | authMiddleware |
| `contextKeyNamespace` | `string` | authMiddleware，用于 per-user client 缓存 |

## API Contracts

### POST /v1/agent-runtime

**请求**:
```
Content-Type: application/json
Authorization: Bearer <token>  // 当 EnableAuth=true 时必需

{
    "kind": "AgentRuntime",    // 可选，handler 会覆盖
    "name": "my-runtime",
    "namespace": "default"
}
```

**成功响应 (200)**:
```json
{
    "sessionId": "550e8400-e29b-41d4-a716-446655440000",
    "sandboxId": "my-runtime-abc12345",
    "sandboxName": "my-runtime-abc12345",
    "entryPoints": [
        {
            "path": "/",
            "protocol": "HTTP",
            "endpoint": "10.244.0.5:8080"
        }
    ]
}
```

**错误响应**:

| 状态码 | 条件 | 响应体 |
|--------|------|--------|
| 400 | JSON 解析失败 | `{"message":"Invalid request body"}` |
| 400 | Validate 失败（name/namespace 为空） | `{"message":"name is required"}` 或 `{"message":"namespace is required"}` |
| 400 | podTemplate 缺失 | `{"message":"agent runtime not found: ... pod template missing"}` |
| 401 | EnableAuth=true 且无 Authorization header | `{"message":"Missing authorization header"}` |
| 401 | TokenReview 失败 | `{"message":"..."}` |
| 404 | Informer 缓存中找不到 AgentRuntime | `{"message":"agent runtime not found"}` |
| 500 | Sandbox 创建超时（>2 分钟） | `{"message":"internal server error"}` |
| 500 | 其他内部错误 | `{"message":"internal server error"}` |

### POST /v1/code-interpreter

与 AgentRuntime 端点结构相同，区别在于：

1. Kind 固定为 `CodeInterpreter`
2. CodeInterpreter 支持 `WarmPoolSize > 0` 时创建 SandboxClaim 而非完整 Sandbox
3. CodeInterpreter 支持 `AuthMode`（`picod` 或 `none`），影响是否注入 `PICOD_AUTH_PUBLIC_KEY` 环境变量
4. 默认端口：若 `spec.Ports` 为空，使用 `[{Port: 8080, Protocol: "HTTP", PathPrefix: "/"}]`

**WarmPool 路径**:
- `WarmPoolSize > 0`: 创建 `SandboxClaim` + 最小化 Sandbox 元数据，`SandboxInfo.Kind = "SandboxClaim"`
- `WarmPoolSize == 0` 或未设置: 创建完整 Sandbox，容器名为 `code-interpreter`

## 创建流程详细设计

### 阶段 1: 请求解析与验证

```
handleAgentRuntimeCreate(c *gin.Context):
  1. var sandboxReq types.CreateSandboxRequest
  2. c.ShouldBindJSON(&sandboxReq) → 400 on error
  3. sandboxReq.Kind = types.AgentRuntimeKind  // 强制覆盖
  4. sandboxReq.Validate() → 400 on error
```

### 阶段 2: 模板获取

```
getAgentRuntime(namespace, name):
  1. informerFactory.Runtime().V1alpha1().AgentRuntimes().Lister().
       AgentRuntimes(namespace).Get(name)
  2. 若返回 k8s errors.IsNotFound → 返回 ErrAgentRuntimeNotFound
  3. 若 runtime.Spec.Template == nil → 返回 ErrTemplateMissing
  4. 返回 *runtimev1alpha1.AgentRuntime
```

CodeInterpreter 路径类似，使用 `CodeInterpreters()` lister。

### 阶段 3: Sandbox 对象构建

**AgentRuntime 路径** (`buildSandboxObject`):

```go
func buildSandboxObject(
    runtime *runtimev1alpha1.AgentRuntime,
    sessionID string,
) (*unstructured.Unstructured, error)
```

- Sandbox 名称: `{workloadName}-{RandString(8)}`（8 位随机小写字母）
- APIVersion: `agents.x-k8s.io/v1alpha1`
- Kind: `Sandbox`
- Labels:
  - `runtime.agentcube.io/session-id`: sessionID
  - `runtime.agentcube.io/workload-name`: runtime.Name
  - `runtime.agentcube.io/sandbox-name`: sandboxName
  - `managed-by`: `agentcube-workload-manager`
- Annotations:
  - `runtime.agentcube.io/idle-timeout`: SessionTimeout 字符串（默认 "15m"）
- Spec:
  - `podTemplate`: 从 `runtime.Spec.Template` 复制 Labels/Annotations/Spec
  - `replicas`: `ptr.To[int32](1)`
  - `lifecycle.shutdownTime`: `now + MaxSessionDuration`（默认 8h）

**CodeInterpreter 路径**:

若 `WarmPoolSize > 0`:
- 调用 `buildSandboxClaimObject()` 创建 SandboxClaim
- APIVersion: `extensions.agents.x-k8s.io/v1alpha1`
- Kind: `SandboxClaim`
- 最小元数据，无完整 PodSpec

否则:
- 构建完整 Sandbox
- 单容器 `code-interpreter`
- Image 从 `CodeInterpreterSandboxTemplate.Image` 获取
- 若 `AuthMode == picod` 且 publicKey 可用: 注入环境变量 `PICOD_AUTH_PUBLIC_KEY`
- 可选字段: Command, Args, Environment, Resources, RuntimeClassName, ImagePullPolicy, ImagePullSecrets

### 阶段 4: 创建与等待

```go
func (sc *sandboxCreator) createSandbox(
    ctx context.Context,
    sandbox *unstructured.Unstructured,
    isWarmPool bool,
    userClient dynamic.Interface,  // auth 启用时使用 per-user client
) (*types.SandboxInfo, error) {
    ns := sandbox.GetNamespace()
    name := sandbox.GetName()

    // 4a. 注册 watcher（在创建之前）
    ch, err := sc.sandboxController.WatchSandboxOnce(ns, name)
    if err != nil { return err }

    // 4b. 占位存储
    sandboxInfo := &types.SandboxInfo{
        Kind:             types.SandboxKind, // 或 SandboxClaimsKind
        SandboxID:        name,
        SandboxNamespace: ns,
        Name:             name,
        SessionID:        sessionID,
        CreatedAt:        time.Now(),
        ExpiresAt:        time.Now().Add(DefaultSandboxTTL),
        Status:           "pending",
    }
    if err := sc.storeClient.StoreSandbox(ctx, sandboxInfo); err != nil {
        return nil, err
    }

    // 4c. 创建 CR
    gvr := SandboxGVR
    if isWarmPool {
        gvr = SandboxClaimGVR
    }
    client := userClient // 或 sc.k8sClient.dynamicClient
    _, err = client.Resource(gvr).Namespace(ns).Create(ctx, sandbox, metav1.CreateOptions{})
    if err != nil {
        // 回滚 store 条目
        sc.storeClient.DeleteSandboxBySessionID(ctx, sessionID)
        return nil, err
    }

    // 4d. 等待 running（最长 2 分钟）
    timeoutCtx, cancel := context.WithTimeout(ctx, 2*time.Minute)
    defer cancel()
    select {
    case <-ch:
        // sandbox 已 running
    case <-timeoutCtx.Done():
        // 超时回滚: 删除已创建的 CR
        deleteCtx, deleteCancel := context.WithTimeout(context.Background(), 30*time.Second)
        defer deleteCancel()
        client.Resource(gvr).Namespace(ns).Delete(deleteCtx, name, metav1.DeleteOptions{})
        sc.storeClient.DeleteSandboxBySessionID(ctx, sessionID)
        return nil, fmt.Errorf("sandbox creation timed out")
    }

    // 4e. 解析 Pod IP 和 entryPoints
    entryPoints, err := sc.resolveEntryPoints(ctx, ns, name, templatePorts)
    if err != nil {
        // 同样需要回滚
        ...
        return nil, err
    }

    // 4f. 更新 store
    sandboxInfo.EntryPoints = entryPoints
    sandboxInfo.Status = "running"
    if err := sc.storeClient.UpdateSandbox(ctx, sandboxInfo); err != nil {
        return nil, err
    }

    return sandboxInfo, nil
}
```

### 阶段 5: Pod IP 解析

```go
func (sc *sandboxCreator) resolvePodIP(
    ctx context.Context,
    sandboxNamespace, sandboxName string,
) (string, error) {
    // 优先使用 sandbox 名称作为 pod 名称
    podName := sandboxName

    // 检查 sandbox 对象上的 annotation
    sandbox, err := sc.k8sClient.dynamicClient.Resource(SandboxGVR).
        Namespace(sandboxNamespace).Get(ctx, sandboxName, metav1.GetOptions{})
    if err == nil {
        if ann := sandbox.GetAnnotations(); ann != nil {
            if pn, ok := ann["agents.x-k8s.io/sandbox-pod-name"]; ok {
                podName = pn
            }
        }
    }

    // 尝试从 informer 缓存获取 pod
    pod, err := sc.k8sClient.podLister.Pods(sandboxNamespace).Get(podName)
    if err == nil {
        if pod.Status.Phase == corev1.PodRunning && pod.Status.PodIP != "" {
            return pod.Status.PodIP, nil
        }
        return "", fmt.Errorf("pod %s is not running (phase: %s)", podName, pod.Status.Phase)
    }

    // 回退: 按 label 列出 pods
    pods, err := sc.k8sClient.podLister.Pods(sandboxNamespace).
        List(labels.SelectorFromSet(map[string]string{
            SandboxNameLabelKey: sandboxName,
        }))
    if err != nil || len(pods) == 0 {
        return "", fmt.Errorf("no pod found for sandbox %s", sandboxName)
    }

    // 选择 owner reference 为 Sandbox 且 name 匹配的 pod
    for _, pod := range pods {
        for _, ref := range pod.OwnerReferences {
            if ref.Kind == "Sandbox" && ref.Name == sandboxName {
                if pod.Status.Phase == corev1.PodRunning && pod.Status.PodIP != "" {
                    return pod.Status.PodIP, nil
                }
            }
        }
    }

    return "", fmt.Errorf("no running pod found for sandbox %s", sandboxName)
}
```

### 阶段 6: EntryPoint 构建

```go
func buildEntryPoints(podIP string, ports []runtimev1alpha1.TargetPort) []types.SandboxEntryPoint {
    var entries []types.SandboxEntryPoint
    for _, p := range ports {
        entries = append(entries, types.SandboxEntryPoint{
            Path:     p.PathPrefix,
            Protocol: string(p.Protocol),
            Endpoint: fmt.Sprintf("%s:%d", podIP, p.Port),
        })
    }
    return entries
}
```

## 错误处理

### 错误分类与 HTTP 映射

| 错误类型 | 来源 | HTTP 状态 | 消息 |
|----------|------|-----------|------|
| JSON 绑定失败 | `gin.ShouldBindJSON` | 400 | `Invalid request body` |
| 验证失败 | `CreateSandboxRequest.Validate` | 400 | `<field> is required` |
| 模板缺失 | `ErrTemplateMissing` | 400 | 包含 `pod template` |
| Not Found | `ErrAgentRuntimeNotFound` / `ErrCodeInterpreterNotFound` | 404 | `agent runtime not found` / `code interpreter not found` |
| 认证失败 | authMiddleware | 401 | TokenReview 错误信息 |
| 超时 | `context.WithTimeout` 2min | 500 | `internal server error` |
| K8s API 错误 | dynamic client Create | 500 | `internal server error` |
| Store 错误 | Redis 操作 | 500 | `internal server error` |

### 回滚策略

创建过程中任何阶段失败后，必须执行回滚：

1. **CR 创建前失败**: 仅需删除 Store 占位记录
2. **CR 创建后、等待 running 超时**: 删除 CR（30s timeout context）+ 删除 Store 记录
3. **Pod IP 解析失败**: 删除 CR + 删除 Store 记录
4. **Store 更新失败**: CR 已创建但 Store 不一致，记录警告日志，CR 由 GC 最终清理

### 超时配置

| 操作 | 超时 |
|------|------|
| 等待 Sandbox running | 2 分钟 |
| 超时后 CR 删除 | 30 秒 |
| GC 单次 tick | 2 分钟 |

## Testing Strategy

### 单元测试

对应 TDD 规范中的 TestCase-WM-001/002/003：

| 测试文件 | 测试目标 |
|----------|----------|
| `handlers_test.go` | `handleAgentRuntimeCreate`, `handleCodeInterpreterCreate` |
| `workload_builder_test.go` | `buildSandboxObject`, `buildSandboxClaimObject` |
| `sandbox_creator_test.go` | `createSandbox` 完整流程 |

#### WM-001: Sandbox 创建成功

```
TestHandleAgentRuntimeCreate_Success:
  Given: 有效的 AgentRuntime 存在于 informer 缓存
  When: POST /v1/agent-runtime 携带合法 JSON
  Then: 返回 200，响应包含 sessionId 和 entryPoints
```

使用 fake clientset + mock store:
- `client-go/clientset/versioned/fake.NewSimpleClientset()` 注册 AgentRuntime
- `miniredis` 或 mock `store.Store` 接口
- mock `SandboxReconciler.WatchSandboxOnce` 返回立即关闭的 channel

#### WM-002: 幂等性

```
TestHandleAgentRuntimeCreate_Idempotent:
  Given: 相同 name 的连续两次请求
  When: 第一次创建成功后再次请求
  Then: 返回相同的 sessionId
```

通过 Store 中已存在的 session 记录实现幂等检查（若 Store 中已有该 name 对应的 session，直接返回已有 sessionId）。

#### WM-003: 非法输入拦截

```
TestHandleAgentRuntimeCreate_MissingPodTemplate:
  Given: AgentRuntime 的 spec.podTemplate 为 nil
  When: POST /v1/agent-runtime
  Then: 返回 400，消息包含 pod template
```

#### 额外测试场景

| 测试 | 描述 |
|------|------|
| `TestHandleCodeInterpreterCreate_WarmPool` | WarmPoolSize > 0 时创建 SandboxClaim |
| `TestHandleCodeInterpreterCreate_DefaultPorts` | Ports 为空时使用默认 8080/HTTP |
| `TestHandleCodeInterpreterCreate_AuthModePicoD` | AuthMode=picod 时注入公钥 |
| `TestHandleCodeInterpreterCreate_AuthModeNone` | AuthMode=none 时不注入公钥 |
| `TestCreateSandbox_Timeout` | 2 分钟超时后回滚 |
| `TestCreateSandbox_RollbackOnIPResolutionFailure` | Pod IP 解析失败时删除 CR |
| `TestResolvePodIP_FromAnnotation` | 使用 `agents.x-k8s.io/sandbox-pod-name` annotation |
| `TestResolvePodIP_FromOwnerReference` | 通过 owner reference 匹配 pod |
| `TestResolvePodIP_PodNotRunning` | Pod 非 Running 阶段时返回错误 |

### 测试基础设施

```go
// testEnv 封装测试所需的依赖
type testEnv struct {
    k8sClient    *K8sClient
    reconciler   *SandboxReconciler
    store        store.Store
    server       *Server
    redis        *miniredis.Miniredis
    fakeClient   *fake.Clientset
    dynamicClient dynamic.Interface
}

func newTestEnv(t *testing.T) *testEnv {
    // 1. 启动 miniredis
    // 2. 创建 fake clientset 并注册 AgentRuntime/CodeInterpreter
    // 3. 创建 fake dynamic client
    // 4. 初始化 K8sClient、SandboxReconciler、Store
    // 5. 构建 Server（禁用 auth 和 TLS）
    // 6. 返回 testEnv
}
```

### 表驱动测试模式

```go
func TestCreateSandboxRequest_Validate(t *testing.T) {
    tests := []struct {
        name    string
        req     types.CreateSandboxRequest
        wantErr string
    }{
        {"valid", types.CreateSandboxRequest{
            Kind: "AgentRuntime", Name: "test", Namespace: "default",
        }, ""},
        {"empty name", types.CreateSandboxRequest{
            Kind: "AgentRuntime", Namespace: "default",
        }, "name is required"},
        {"empty namespace", types.CreateSandboxRequest{
            Kind: "AgentRuntime", Name: "test",
        }, "namespace is required"},
        {"invalid kind", types.CreateSandboxRequest{
            Kind: "Unknown", Name: "test", Namespace: "default",
        }, "kind is required"},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            err := tt.req.Validate()
            if tt.wantErr == "" {
                assert.NoError(t, err)
            } else {
                assert.ErrorContains(t, err, tt.wantErr)
            }
        })
    }
}
```

### 集成测试

E2E 测试通过 Kind 集群验证完整流程：

```
TestE2E_CreateAgentRuntimeSandbox:
  1. 部署 AgentCube（Helm install）
  2. 创建 ServiceAccount 并获取 token
  3. POST /v1/agent-runtime 创建 sandbox
  4. 验证响应包含 sessionId 和 entryPoints
  5. 通过 entryPoint 访问 sandbox 验证连通性
  6. DELETE /v1/agent-runtime/sessions/:sessionId 清理
```

E2E fixture: `echo_agent.yaml`（简单的 echo server AgentRuntime 定义）。

### 测试覆盖率目标

- 测试代码/业务代码比例 > 0.4
- 每个源文件对应一个 `*_test.go`
- 核心路径（创建成功、超时回滚、验证失败）必须覆盖
- 使用 `go test -race -v -coverprofile=coverage.out -coverpkg=./pkg/... ./pkg/...` 验证

## 文件结构

```
pkg/workloadmanager/
  server.go              — Server struct, Config, Start(), HTTP 路由注册
  handlers.go            — handleHealth, handleAgentRuntimeCreate, handleCodeInterpreterCreate, handleDeleteSandbox
  workload_builder.go    — buildSandboxObject, buildSandboxClaimObject, createSandbox, resolvePodIP, buildEntryPoints
  sandbox_creator.go     — sandboxCreator struct 和 createSandbox 主流程
  informers.go           — GVR 变量定义, Informers struct, sync
  sandbox_controller.go  — SandboxReconciler, WatchSandboxOnce, getSandboxStatus
  garbage_collector.go   — garbageCollector, gcLoop
  auth.go                — authMiddleware, validateServiceAccountToken, context keys
  k8s_client.go          — K8sClient, ClientCache, GetOrCreateUserK8sClient
  defaults.go            — 常量: DefaultSandboxTTL, DefaultSandboxIdleTimeout, label/annotation keys
pkg/workloadmanager/
  server_test.go
  handlers_test.go
  workload_builder_test.go
  sandbox_creator_test.go
  sandbox_controller_test.go
  garbage_collector_test.go
  auth_test.go
  k8s_client_test.go
```

## 与 client-go 的集成

本处理器使用 `github.com/volcano-sh/agentcube/client-go` 中的以下组件：

| 组件 | 用途 |
|------|------|
| `clientset/versioned.Interface` | 获取 typed client（读取 AgentRuntime/CodeInterpreter） |
| `typed/runtime/v1alpha1.AgentRuntimeInterface` | 直接 CRUD AgentRuntime（备用路径，主要使用 lister） |
| `typed/runtime/v1alpha1.CodeInterpreterInterface` | 直接 CRUD CodeInterpreter（备用路径） |
| `informers/externalversions.SharedInformerFactory` | informer 生命周期管理 |
| `informers/externalversions/runtime/v1alpha1.AgentRuntimeInformer` | AgentRuntime informer + lister |
| `informers/externalversions/runtime/v1alpha1.CodeInterpreterInformer` | CodeInterpreter informer + lister |
| `listers/runtime/v1alpha1.AgentRuntimeLister` | 只读查询 AgentRuntime |
| `listers/runtime/v1alpha1.CodeInterpreterLister` | 只读查询 CodeInterpreter |
| `clientset/versioned/fake.*` | 单元测试中的 fake clientset |

Informer 初始化流程：

```go
func (s *Server) syncInformers(timeout time.Duration) error {
    s.informers.Start(s.ctx.Done())
    synced := s.informers.WaitForCacheSync(s.ctx.Done())
    // 验证 AgentRuntime 和 CodeInterpreter informer 都 sync 完成
    // 超时 1 分钟
}
```

## 关键决策

### 为什么使用 dynamic client 创建 Sandbox 而非 typed client

Sandbox 和 SandboxClaim 是外部 CRD（`sigs.k8s.io/agent-sandbox`），不在 agentcube 的 client-go 生成范围内。使用 `dynamic.Interface` + `unstructured.Unstructured` 是操作未知 schema CRD 的标准做法。

### 为什么 Watcher 注册在 CR 创建之前

存在竞态条件：如果先创建 CR 再注册 watcher，Sandbox 可能在 watcher 注册前就进入 running 状态，导致永久等待。因此必须先 `WatchSandboxOnce` 注册 channel，再创建 CR。

### 为什么需要 Store 占位记录

在等待 Sandbox running 期间（最长 2 分钟），Store 中已有记录可以：
1. 防止重复创建（幂等性检查）
2. 让 GC 感知到进行中的创建操作
3. 提供创建失败时的回滚目标

### 超时回滚策略

2 分钟超时是 spec 规定的硬性要求。超时后必须删除已创建的 CR，否则会产生孤儿 Sandbox 资源。删除操作使用独立的 30 秒 timeout context，避免因删除失败阻塞响应。
