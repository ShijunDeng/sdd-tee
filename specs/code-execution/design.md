# AR-015 — PicoD 命令执行 API Design

## Overview

| Item | Value |
|------|-------|
| AR | AR-015 — PicoD 命令执行 API |
| Module | `pkg/picod` |
| Language | Go |
| Size | M |
| Stage | ST-1 completed |

PicoD 是一个运行在 Sandbox Pod 内的 HTTP 守护进程，提供命令执行、文件管理和健康检查 API。所有 `/api` 路由通过 JWT RS256 认证保护，使用 RSA 公钥验证由 Router 签发的短期 token。命令在 workspace 目录 jail 内执行，路径安全通过 `sanitizePath` 双重校验（逻辑检查 + 符号链接解析）防止目录穿越。

## Architecture

### 组件交互

```
Router (带 JWT 私钥)
  → 签发短期 RS256 token
    → 转发请求到 Sandbox Pod IP:8080
      → PicoD Server (pkg/picod)
        → AuthMiddleware 验证 JWT（RSA 公钥）
          → ExecuteHandler: exec.CommandContext 执行命令
          → UploadFileHandler: 写入文件到 workspace
          → ListFilesHandler: 列出目录内容
          → DownloadFileHandler: 下载文件
        → HealthCheckHandler: 无认证，返回服务状态
```

### 启动流程

```
cmd/picod/main.go
  → flag.Parse(-port=8080, -workspace="")
  → klog.InitFlags(nil)
  → picod.NewServer(Config{Port, Workspace})
    → gin.SetMode(gin.ReleaseMode)
    → gin.New() + Logger + Recovery 全局中间件
    → AuthManager.LoadPublicKeyFromEnv()
      → 读取 PICOD_AUTH_PUBLIC_KEY
      → PEM 解码 → x509.ParsePKIXPublicKey → 断言 *rsa.PublicKey
      → 失败则 klog.Fatalf（无法启动）
    → 注册路由
      → /health (无认证)
      → /api/* (AuthMiddleware 保护)
        → POST /api/execute
        → POST /api/files
        → GET /api/files
        → GET /api/files/*path
    → setWorkspace() 解析 workspace 绝对路径
  → server.Run()
    → http.Server{Addr, Handler, ReadHeaderTimeout: 10s}
    → ListenAndServe()
```

### 关键依赖

| Dependency | Version | Purpose |
|------------|---------|---------|
| `github.com/gin-gonic/gin` | `v1.10.0` | HTTP 框架（ReleaseMode） |
| `github.com/golang-jwt/jwt/v5` | `v5.2.2` | JWT RS256 验证 |
| `k8s.io/klog/v2` | `v2.130.1` | 结构化日志 |
| `crypto/rsa`, `crypto/x509`, `encoding/pem` | stdlib | RSA 公钥解析 |
| `os/exec`, `context` | stdlib | 命令执行与超时控制 |
| `path/filepath`, `os` | stdlib | 路径安全与文件操作 |

## Data Structures

### Server

```go
type Server struct {
    engine      *gin.Engine
    config      Config
    authManager *AuthManager
    startTime   time.Time
    workspaceDir string
}
```

| Field | Type | Description |
|-------|------|-------------|
| `engine` | `*gin.Engine` | Gin HTTP 引擎 |
| `config` | `Config` | 服务器配置 |
| `authManager` | `*AuthManager` | JWT 认证管理器 |
| `startTime` | `time.Time` | 服务启动时间（`time.Now()` in `NewServer`） |
| `workspaceDir` | `string` | workspace 绝对路径（符号链接已解析） |

### Config

```go
type Config struct {
    Port      int    `json:"port"`
    Workspace string `json:"workspace"`
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `Port` | `8080` | HTTP 监听端口 |
| `Workspace` | `""` → CWD | 文件操作根目录 |

### AuthManager

```go
type AuthManager struct {
    publicKey *rsa.PublicKey
    mutex     sync.RWMutex
}
```

| Field | Description |
|-------|-------------|
| `publicKey` | RSA 公钥（用于 JWT 验证） |
| `mutex` | 读写锁，保护公钥并发访问 |

### Request/Response Structs

#### Execute

```go
type ExecuteRequest struct {
    Command    []string          `json:"command" binding:"required"`
    Timeout    string            `json:"timeout"`
    WorkingDir string            `json:"working_dir"`
    Env        map[string]string `json:"env"`
}

type ExecuteResponse struct {
    Stdout    string    `json:"stdout"`
    Stderr    string    `json:"stderr"`
    ExitCode  int       `json:"exit_code"`
    Duration  float64   `json:"duration"`
    StartTime time.Time `json:"start_time"`
    EndTime   time.Time `json:"end_time"`
}
```

#### Files

```go
type FileInfo struct {
    Path     string    `json:"path"`
    Size     int64     `json:"size"`
    Mode     string    `json:"mode"`
    Modified time.Time `json:"modified"`
}

type UploadFileRequest struct {
    Path    string `json:"path" binding:"required"`
    Content string `json:"content" binding:"required"`
    Mode    string `json:"mode"`
}

type FileEntry struct {
    Name     string    `json:"name"`
    Size     int64     `json:"size"`
    Modified time.Time `json:"modified"`
    Mode     string    `json:"mode"`
    IsDir    bool      `json:"is_dir"`
}

type ListFilesResponse struct {
    Files []FileEntry `json:"files"`
}
```

### Constants

| Name | Value | File | Description |
|------|-------|------|-------------|
| `TimeoutExitCode` | `124` | `execute.go` | 命令超时退出码 |
| `MaxBodySize` | `32 << 20` (32 MiB) | `auth.go` | 请求体最大字节数 |
| `PublicKeyEnvVar` | `"PICOD_AUTH_PUBLIC_KEY"` | `auth.go` | 公钥环境变量名 |
| `maxFileMode` | `0777` | `files.go` | 文件模式上限 |
| Default execute timeout | `60 * time.Second` | `execute.go` | 命令执行默认超时 |
| Default file mode | `0644` | `files.go` | 文件创建默认权限 |
| Dir creation mode | `0755` | `files.go` | 目录创建权限 |

## API Contracts

### Route Registration

```
GET  /health                    → HealthCheckHandler（无认证）
POST /api/execute               → ExecuteHandler（JWT 认证）
POST /api/files                 → UploadFileHandler（JWT 认证）
GET  /api/files                 → ListFilesHandler（JWT 认证）
GET  /api/files/*path           → DownloadFileHandler（JWT 认证）
```

路由注册模式：

```go
api := engine.Group("/api")
api.Use(s.authManager.AuthMiddleware())
{
    api.POST("/execute", s.ExecuteHandler)
    api.POST("/files", s.UploadFileHandler)
    api.GET("/files", s.ListFilesHandler)
    api.GET("/files/*path", s.DownloadFileHandler)
}
engine.GET("/health", s.HealthCheckHandler)
```

### POST /api/execute — 命令执行

**Request:**

| Header | Required | Value |
|--------|----------|-------|
| `Content-Type` | Yes | `application/json` |
| `Authorization` | Yes | `Bearer <jwt-token>` |

**Body (`ExecuteRequest`):**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `command` | `[]string` | Yes | — | 命令及参数，`command[0]` 为可执行文件 |
| `timeout` | `string` | No | `"60s"` | Go `time.ParseDuration` 格式 |
| `working_dir` | `string` | No | workspace 根目录 | 相对于 workspace 的路径 |
| `env` | `map[string]string` | No | — | 额外环境变量 |

**Response (200 OK):**

```json
{
    "stdout": "command output\n",
    "stderr": "",
    "exit_code": 0,
    "duration": 0.042,
    "start_time": "2026-04-10T12:00:00Z",
    "end_time": "2026-04-10T12:00:00Z"
}
```

**Error Responses:**

| Status | Body | Condition |
|--------|------|-----------|
| 400 | `{"error": "...", "code": 400}` | JSON 绑定失败 |
| 400 | `{"error": "command cannot be empty", "code": 400}` | `command` 为空数组 |
| 400 | `{"error": "Invalid timeout format: ...", "code": 400}` | `timeout` 非合法 duration |
| 400 | `{"error": "Invalid working directory: ...", "code": 400}` | `working_dir` 路径穿越 |

**执行逻辑:**

1. `c.ShouldBindJSON(&req)` 解析请求
2. 校验 `len(req.Command) > 0`
3. 解析 `timeout`：空字符串 → `60s`，否则 `time.ParseDuration(req.Timeout)`
4. 解析 `working_dir`：非空则 `sanitizePath(req.WorkingDir)`
5. 构建 `cmd.Env`：`os.Environ()` + `key=value` 对
6. `exec.CommandContext(ctx, req.Command[0], req.Command[1:]...)`
7. `cmd.Stdout` / `cmd.Stderr` → `bytes.Buffer`，**不设置 stdin**
8. `cmd.Start()` → 记录 `startTime`
9. `cmd.Wait()` → 记录 `endTime`
10. 退出码判定：
    - `context.DeadlineExceeded` → `TimeoutExitCode` (124)，stderr 追加超时信息
    - `cmd.ProcessState != nil` → `cmd.ProcessState.ExitCode()`
    - 其他错误 → `1`，stderr 追加错误信息

### POST /api/files — 文件上传

**Content-Type 检测:**

```go
contentType := c.ContentType()
if strings.HasPrefix(contentType, "multipart/form-data") {
    s.handleMultipartUpload(c)
} else {
    s.handleJSONBase64Upload(c)
}
```

#### Multipart Upload

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | `string` | Yes | 相对于 workspace 的文件路径 |
| `file` | `file` | Yes | 上传的文件流 |
| `mode` | `string` | No | 八进制文件模式（如 `"0644"`） |

**处理流程:**

1. 获取 `path` 和 `file`
2. `sanitizePath(path)` 安全校验
3. `os.MkdirAll(filepath.Dir(safePath), 0755)` 创建父目录
4. 创建文件 → `io.Copy` 写入流
5. `parseFileMode(mode)` → `os.Chmod`
6. 返回 `FileInfo`，`path` 为相对于 workspace 的路径

#### JSON Base64 Upload

**Body (`UploadFileRequest`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | `string` | Yes | 相对于 workspace 的文件路径 |
| `content` | `string` | Yes | Base64 标准编码的文件内容 |
| `mode` | `string` | No | 八进制文件模式 |

**处理流程:**

1. `c.ShouldBindJSON(&req)`
2. `base64.StdEncoding.DecodeString(req.Content)`
3. `sanitizePath(req.Path)`
4. `os.MkdirAll` → `os.WriteFile`（或 `os.Create` + `Write`）
5. `parseFileMode` → `os.Chmod`
6. 返回 `FileInfo`

**Error Responses:**

| Status | Body | Condition |
|--------|------|-----------|
| 400 | `{"error": "Missing 'path' parameter", "code": 400}` | multipart 缺少 path |
| 400 | `{"error": "Missing 'file' in request", "code": 400}` | multipart 缺少 file |
| 400 | `{"error": "Invalid base64 content", "code": 400}` | Base64 解码失败 |
| 400 | `{"error": "Access denied: ...", "code": 400}` | 路径穿越 |
| 500 | `{"error": "...", "code": 500}` | 文件写入失败 |

### GET /api/files — 目录列表

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | `string` | Yes | 相对于 workspace 的目录路径 |

**Response (200 OK):**

```json
{
    "files": [
        {
            "name": "main.py",
            "size": 1024,
            "modified": "2026-04-10T12:00:00Z",
            "mode": "0644",
            "is_dir": false
        },
        {
            "name": "output",
            "size": 4096,
            "modified": "2026-04-10T12:00:00Z",
            "mode": "0755",
            "is_dir": true
        }
    ]
}
```

**处理流程:**

1. `path := c.Query("path")`，空则返回 400
2. `sanitizePath(path)`
3. `os.ReadDir(safePath)`
4. 遍历条目，`entry.Info()` 获取元数据
5. 跳过 `Info()` 失败的条目
6. 返回 `ListFilesResponse`

**Error Responses:**

| Status | Body | Condition |
|--------|------|-----------|
| 400 | `{"error": "Missing 'path' query parameter", "code": 400}` | 缺少 path 参数 |
| 400 | `{"error": "Access denied: ...", "code": 400}` | 路径穿越 |
| 404 | `{"error": "Directory not found", "code": 404}` | 目录不存在 |
| 500 | `{"error": "...", "code": 500}` | 读取失败 |

### GET /api/files/*path — 文件下载

**Path Parameter:**

| Param | Description |
|-------|-------------|
| `*path` | 相对于 workspace 的文件路径（Gin wildcard） |

**Response Headers:**

| Header | Value |
|--------|-------|
| `Content-Description` | `File Transfer` |
| `Content-Transfer-Encoding` | `binary` |
| `Content-Disposition` | `attachment; filename="<basename>"` |
| `Content-Type` | `mime.TypeByExtension(ext)` 或 `application/octet-stream` |

**处理流程:**

1. `path := c.Param("path")` → `strings.TrimPrefix(path, "/")`
2. `sanitizePath(path)`
3. `os.Stat(safePath)` 校验为普通文件（非目录）
4. 设置响应头
5. `c.File(safePath)` 流式返回文件内容

**Error Responses:**

| Status | Body | Condition |
|--------|------|-----------|
| 400 | `{"error": "Access denied: ...", "code": 400}` | 路径穿越 |
| 400 | `{"error": "Path is a directory, not a file", "code": 400}` | 目标是目录 |
| 404 | `{"error": "File not found", "code": 404}` | 文件不存在 |
| 500 | `{"error": "...", "code": 500}` | stat 失败 |

### GET /health — 健康检查

**无认证要求。**

**Response (200 OK):**

```json
{
    "status": "ok",
    "service": "PicoD",
    "version": "0.0.1",
    "uptime": "2h30m15s"
}
```

## Error Handling

### 错误响应格式

**通用错误（400/500）:**

```json
{
    "error": "描述信息",
    "code": 400
}
```

**认证错误（401）:**

```json
{
    "error": "Unauthorized",
    "code": 401,
    "detail": "具体原因"
}
```

### 错误分类

| Category | HTTP Status | Examples |
|----------|-------------|----------|
| Client Error | 400 | JSON 绑定失败、空命令、无效 timeout、路径穿越、无效 Base64 |
| Authentication | 401 | 缺少 Authorization header、Bearer 格式错误、JWT 验证失败 |
| Not Found | 404 | 文件/目录不存在 |
| Server Error | 500 | 命令执行异常、文件写入失败、内部状态错误 |

### 命令执行错误处理

```
┌─────────────────────────────────────────┐
│           Command Execution              │
├─────────────────────────────────────────┤
│ 1. ShouldBindJSON 失败                   │
│    → 400 {"error": binder error}         │
│                                          │
│ 2. len(Command) == 0                     │
│    → 400 {"error": "command cannot..."}  │
│                                          │
│ 3. ParseDuration 失败                     │
│    → 400 {"error": "Invalid timeout..."} │
│                                          │
│ 4. sanitizePath(working_dir) 失败         │
│    → 400 {"error": "Invalid working..."} │
│                                          │
│ 5. cmd.Wait() 返回错误                    │
│    ├─ context.DeadlineExceeded            │
│    │   → exit_code = 124                 │
│    │   → stderr += "command timed out"   │
│    ├─ ProcessState != nil                 │
│    │   → exit_code = ProcessState.ExitCode() │
│    └─ 其他                                │
│        → exit_code = 1                   │
│        → stderr += err.Error()           │
│                                          │
│ 6. 正常完成                               │
│    → 200 ExecuteResponse                 │
└─────────────────────────────────────────┘
```

### JWT 认证错误处理

```
┌─────────────────────────────────────────┐
│           AuthMiddleware                 │
├─────────────────────────────────────────┤
│ 1. Authorization header 为空              │
│    → 401 {"error": "Missing header",    │
│            "detail": "JWT required"}     │
│                                          │
│ 2. Bearer 格式错误                        │
│    → 401 {"error": "Invalid format",    │
│            "detail": "Use Bearer <token>"}│
│                                          │
│ 3. JWT 验证失败                           │
│    → 401 {"error": "Invalid token",     │
│            "detail": "<verification err>"}│
│                                          │
│ 4. 验证通过                               │
│    → Body 包装 MaxBytesReader (32 MiB)   │
│    → c.Next()                            │
└─────────────────────────────────────────┘
```

### 路径安全（sanitizePath）

`sanitizePath` 实现双重校验防止目录穿越攻击：

```
sanitizePath(p):
  1. workspaceDir 为空 → error "workspace directory not initialized"
  2. resolvedWorkspace = filepath.EvalSymlinks(workspaceDir)
     → 失败则 fallback 到 filepath.Abs 或 filepath.Clean
  3. resolvedWorkspace = filepath.Clean(resolvedWorkspace)
  4. cleanPath = filepath.Clean(p)
     → 绝对路径则去除前导 "/"
  5. fullPathCandidate = filepath.Clean(filepath.Join(resolvedWorkspace, cleanPath))
  6. relPath, relErr = filepath.Rel(resolvedWorkspace, fullPathCandidate)
     → relErr != nil → error "Access denied"
     → relPath 以 ".." 开头或等于 ".." → error "Access denied"
  7. resolvedFinalPath = filepath.EvalSymlinks(fullPathCandidate)
     → 成功: 再次 filepath.Rel 校验，通过则返回 resolvedFinalPath
     → 失败 (路径不存在): 返回 fullPathCandidate (已通过逻辑校验)
```

**安全特性:**

- 符号链接解析：防止通过 symlink 穿越 workspace
- 双重校验：逻辑路径检查 + 实际文件系统解析
- 不存在路径：允许创建（用于上传），但限制在 workspace 内

## Testing Strategy

### 测试分层

```
┌─────────────────────────────────────────┐
│           测试金字塔                      │
├─────────────────────────────────────────┤
│                                          │
│              E2E 测试                     │
│         (完整 HTTP 请求)                  │
│              /    \                      │
│         集成测试   边界测试                │
│        (Gin test)  (路径安全)             │
│              \    /                      │
│            单元测试                       │
│         (函数/方法级)                     │
│                                          │
└─────────────────────────────────────────┘
```

### 单元测试

| 测试目标 | 测试文件 | 覆盖内容 |
|----------|----------|----------|
| `sanitizePath` | `files_test.go` | 正常路径、绝对路径、`..` 穿越、符号链接穿越、空 workspace |
| `parseFileMode` | `files_test.go` | 有效八进制、无效字符串、超过 0777、空字符串 |
| `AuthManager.LoadPublicKeyFromEnv` | `auth_test.go` | 有效 RSA 公钥、空环境变量、无效 PEM、非 RSA 密钥 |
| `AuthManager.AuthMiddleware` | `auth_test.go` | 有效 JWT、过期 JWT、错误签名、HS256 拒绝、缺少 header、格式错误 |
| `ExecuteHandler` | `execute_test.go` | 正常执行、超时、空命令、无效 timeout、working_dir、环境变量 |
| `UploadFileHandler` | `files_test.go` | multipart 上传、JSON Base64 上传、无效 Base64、路径穿越 |
| `ListFilesHandler` | `files_test.go` | 有效目录、空 path、目录不存在 |
| `DownloadFileHandler` | `files_test.go` | 有效文件、目录、路径穿越、文件不存在 |
| `HealthCheckHandler` | `health_test.go` | 响应字段、uptime 增长 |

### 集成测试

| 测试场景 | 方法 | 验证点 |
|----------|------|--------|
| 完整命令执行流程 | `httptest.NewRecorder` + `gin.CreateTestContext` | JWT 认证 → 命令执行 → 响应格式 |
| 文件上传下载循环 | 上传文件 → 列出目录 → 下载文件 → 校验内容 | 端到端文件一致性 |
| 超时机制 | 执行 `sleep 10` + `timeout: "1s"` | exit_code=124, duration≈1s |
| 并发请求 | goroutine 发送多个请求 | 无数据竞争、响应隔离 |

### 测试工具

| Tool | Purpose |
|------|---------|
| `github.com/stretchr/testify` | 断言库（`assert`, `require`） |
| `github.com/gin-gonic/gin` test mode | HTTP handler 测试 |
| `net/http/httptest` | 模拟 HTTP 请求/响应 |
| `crypto/rsa`, `crypto/x509` | 测试用 RSA 密钥对生成 |
| `github.com/golang-jwt/jwt/v5` | 测试用 JWT 签发（私钥） |
| `os.MkdirTemp` | 临时 workspace 目录 |

### 测试用例矩阵

#### ExecuteHandler

| # | Scenario | Command | Timeout | Expected |
|---|----------|---------|---------|----------|
| E1 | 正常执行 | `["echo", "hello"]` | `""` | exit_code=0, stdout="hello\n" |
| E2 | 非零退出 | `["sh", "-c", "exit 42"]` | `""` | exit_code=42 |
| E3 | 超时 | `["sleep", "10"]` | `"1s"` | exit_code=124 |
| E4 | 自定义 timeout | `["echo", "ok"]` | `"500ms"` | exit_code=0, duration≤0.5s |
| E5 | 无效 timeout | `["echo", "ok"]` | `"invalid"` | 400 |
| E6 | 空命令 | `[]` | `""` | 400 |
| E7 | working_dir | `["pwd"]` | `""`, working_dir="sub" | stdout 包含 sub |
| E8 | working_dir 穿越 | `["pwd"]` | `""`, working_dir="../.." | 400 |
| E9 | 环境变量 | `["env"]` | `""`, env={"FOO": "bar"} | stdout 包含 FOO=bar |
| E10 | 命令不存在 | `["nonexistent_cmd"]` | `""` | exit_code≠0, stderr 包含错误 |

#### AuthMiddleware

| # | Scenario | Token | Expected |
|---|----------|-------|----------|
| A1 | 有效 JWT | RS256 signed, 未过期 | 200, 继续处理 |
| A2 | 过期 JWT | RS256 signed, exp 在过去 | 401 |
| A3 | 错误签名 | 用错误私钥签名 | 401 |
| A4 | HS256 token | HMAC 签名 | 401 (拒绝非 RSA) |
| A5 | 缺少 header | 无 Authorization | 401 |
| A6 | 格式错误 | `Authorization: Token xxx` | 401 |
| A7 | 无 Bearer 前缀 | `Authorization: xxx` | 401 |

#### File Operations

| # | Scenario | Operation | Expected |
|---|----------|-----------|----------|
| F1 | Multipart 上传 | POST /api/files (multipart) | 200, FileInfo |
| F2 | JSON Base64 上传 | POST /api/files (JSON) | 200, FileInfo |
| F3 | 无效 Base64 | POST /api/files (invalid base64) | 400 |
| F4 | 路径穿越上传 | path="../../etc/passwd" | 400 |
| F5 | 目录列表 | GET /api/files?path=. | 200, FileEntry[] |
| F6 | 缺失 path 参数 | GET /api/files | 400 |
| F7 | 文件下载 | GET /api/files/test.txt | 200, 文件内容 + headers |
| F8 | 下载目录 | GET /api/files/subdir/ | 400 "not a file" |
| F9 | 下载不存在 | GET /api/files/missing | 404 |

### 基准测试

| Benchmark | Purpose |
|-----------|---------|
| `BenchmarkExecuteHandler` | 命令执行吞吐量 |
| `BenchmarkUploadFile` | 文件上传性能 |
| `BenchmarkSanitizePath` | 路径校验开销 |
| `BenchmarkAuthMiddleware` | JWT 验证延迟 |

### 测试环境要求

- 临时目录：`os.MkdirTemp("", "picod-test-*")` 作为 workspace
- RSA 密钥对：每次测试生成或使用固定测试密钥
- 环境变量：`PICOD_AUTH_PUBLIC_KEY` 在测试中通过 `os.Setenv` 设置
- 清理：`defer os.RemoveAll(tempDir)` 确保测试后清理
