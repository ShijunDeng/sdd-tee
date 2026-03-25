# AgentCube 测试用例规范 (TDD Specification)

要求 AI 在实现业务代码时，同步完成以下测试用例，作为实现完成度的判定标准。

## 1. 核心控制器测试 (Workload Manager)
- **TestCase-WM-001**: 验证 Sandbox 创建接口。输入合法 `AgentRuntime` 定义，预期返回 `200 OK` 及 `sessionId`。
- **TestCase-WM-002**: 验证 Sandbox 幂等性。相同 `name` 连续调用两次，预期返回相同 `sessionId`。
- **TestCase-WM-003**: 验证非法输入拦截。输入缺失 `podTemplate` 的请求，预期返回 `400 Bad Request`。

## 2. 路由与会话测试 (Router)
- **TestCase-RT-001**: 验证 Auth 拦截。未携带 Bearer Token 请求 `/v1/execute`，预期返回 `401 Unauthorized`。
- **TestCase-RT-002**: 验证会话路由。模拟 Redis 中存在会话，Router 成功将请求转发至后端（Mock 后端）。
- **TestCase-RT-003**: 验证会话过期。模拟 Redis 中 Token 已失效，返回 `404 Not Found`。

## 3. 存储层测试 (Store)
- **TestCase-ST-001**: Redis Set/Get 验证。成功存储并检索 `SessionInfo` 结构体。
- **TestCase-ST-002**: 过期时间验证。验证 Key 携带正确的 TTL（默认 24h）。

## 4. 编码执行引擎测试 (PicoD)
- **TestCase-PD-001**: Python 代码执行。发送 `print("hello")`，预期 stdout 为 `hello\n`，exitCode 为 0。
- **TestCase-PD-002**: 错误处理。发送语法错误代码，预期 stderr 包含 `SyntaxError`。

## 5. Python SDK 测试
- **TestCase-SDK-001**: 上下文管理器验证。使用 `with CodeInterpreterClient(...) as client:` 确保结束时自动调用 `close()`。
- **TestCase-SDK-002**: 异常映射。服务端返回 500 时，SDK 抛出自定义 `AgentCubeError` 而非原始 HTTP 错误。

## 实施要求
- **Go 代码**：必须位于对应的 `*_test.go` 中，可通过 `go test ./...` 运行。
- **Python 代码**：必须位于 `tests/` 目录或 `test_*.py` 文件中，可通过 `pytest` 运行。
