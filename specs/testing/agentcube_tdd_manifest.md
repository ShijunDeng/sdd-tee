# AgentCube 核心模块测试契约 (TDD Manifest)

本规范定义了系统各核心组件必须实现的最小测试集。未通过以下测试用例的实现将被判定为“跑偏”。

## 1. Workload Manager (Go) - 核心准入测试
- **Func: `CreateSandbox`**
    - **Test-WM-1**: 必须 Mock Kubernetes Client，验证 `sandbox` 资源被正确创建。
    - **Test-WM-2**: 验证 Session 冲突处理（同名 Sandbox 冲突时返回 409 或恢复现有会话）。
    - **Test-WM-3**: 验证 Pod 状态同步逻辑。模拟 Pod 变为 `Running` 状态，验证 API 返回正确的 `Endpoint`。
- **Func: `DeleteSession`**
    - **Test-WM-4**: 验证物理资源的清理。确保调用了 K8s Delete API 且 Redis 记录同步删除。

## 2. Router (Go) - 高并发与安全测试
- **Middleware: `AuthMiddleware`**
    - **Test-RT-1**: 构造非法 JWT，验证返回 `401 Unauthorized`。
    - **Test-RT-2**: 构造过期 JWT，验证返回 `Token Expired`。
- **Proxy Logic: `HandleProxy`**
    - **Test-RT-3**: 模拟后端超时，验证 Proxy 正确处理 `Gateway Timeout` 且不崩溃。
    - **Test-RT-4**: 验证 Header 透传（Host, X-Forwarded-For 等）。

## 3. Session Store (Go) - 强一致性测试
- **Store Interface: `RedisStore` / `ValkeyStore`**
    - **Test-ST-1**: 验证对象序列化与反序列化（SessionInfo -> JSON -> SessionInfo）。
    - **Test-ST-2**: 并发写测试。模拟 100 个并发请求写入同一 Session，验证无 Data Race。

## 4. PicoD (Go) - 执行引擎隔离测试
- **Executor: `RunCode`**
    - **Test-PD-1**: 验证资源限制（如 OOM）。模拟大内存分配，验证进程被正确杀掉并返回错误。
    - **Test-PD-2**: 验证 Stdout 分块读取。处理超过 1MB 的输出，验证无缓冲区溢出。

## 5. Python SDK & CLI - 兼容性与易用性测试
- **Class: `CodeInterpreterClient`**
    - **Test-SDK-1**: 验证所有 HTTP 状态码映射。404 -> `NotFoundError`, 429 -> `RateLimitError`。
    - **Test-SDK-2**: 验证文件上传协议。构造二进制流，验证 Multipart 封装符合 Router 规范。
- **CLI: `kubectl-agentcube`**
    - **Test-CLI-1**: 验证 `run` 命令的参数解析。测试 `--image`, `--env` 等参数的正确合并。

## 物理指标要求
1.  **测试/代码行数比 (T/C Ratio)**: 必须 > 0.4 (即每 100 行代码至少 40 行测试)。
2.  **用例完整性**: 每个源文件（`*.go`, `*.py`）必须存在对应的 `*_test.go` 或 `test_*.py`。
