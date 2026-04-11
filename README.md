# SDD-TEE v5.1 — SDD Token Efficiency Evaluation

基于 **CodeSpec 工作流** 与 **OpenSpec OPSX 工具链**的 AI Coding Assistant Token 效率评估框架。

通过将真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 拆解为 **43 个细粒度 AR（分配需求）**，
每个 AR 走完整的 SDD 流程（`/opsx:new` → `/opsx:ff` → `/opsx:apply` → `/opsx:verify` → `/opsx:archive`），
**量化 8 个阶段（ST-0~ST-7）× 5 个维度的 Token 消耗**，为 Token 提效研究提供评估基线。

## v5.1 架构

```
engine.py (benchmark driver)
  → adapters/*.py (CLI tool subprocess)
    → LiteLLM Proxy JSONL (authoritative token log, port 4000)
      → auditor.py (time-window filtering, cost calculation)
        → _full.json (schema-compliant output)
```

**核心特性**:
- **LiteLLM Proxy 为唯一权威数据源**: 每次 API 调用均记录精确 token 用量
- **Native CLI 兜底解析**: 适配器从 CLI 工具输出中解析 token，作为 Proxy 不可用时的回退
- **Reconciliation 机制**: 每完成一个 AR 后重新解析全部日志，修正 api_calls 膨胀
- **零伪造数据**: dry-run 模式仅打印 prompt，绝不估算 token

## 8 阶段工作流

| 阶段 | 名称 | 说明 |
|------|------|------|
| ST-0 | AR 输入 | 读取 AR 描述文件，构建上下文 |
| ST-1 | 需求澄清 | 模型理解需求、提出澄清问题 |
| ST-2 | Spec 增量设计 | 生成/修改 OpenSpec 规格文件 |
| ST-3 | Design 增量设计 | 生成/修改设计文档 |
| ST-4 | 任务拆解 | 将设计分解为可执行任务列表 |
| ST-5 | 开发实现 | 实际代码编写与修改 |
| ST-6 | 一致性验证 | 验证实现与 Spec/Design 一致性 |
| ST-6.5 | 原始代码等价性验证 | 确保不破坏原有功能 |
| ST-7 | 合并归档 | 将变更合并至主分支并归档 |

## 5 维指标体系

| 维度 | 编码 | 指标示例 |
|------|------|----------|
| 阶段维度 | ST-0 ~ ST-7 | 各阶段 Input/Output/Cache Tokens、迭代数、耗时 |
| 角色维度 | RT-AI / RT-HUMAN | AI Token、人工输入 Token、人机比、预制规范（单独标注） |
| 效率维度 | ET-LOC / ET-FILE / ET-TASK | Token/LOC、Token/File、Token/Task、Token/AR |
| 质量维度 | QT-COV / QT-CONSIST | Token/覆盖率、Token/一致性、Token/可用率、Token/Bug |
| 分布维度 | PT-DESIGN / PT-DEV | 设计/开发/验证阶段占比、峰值阶段 |

## 快速开始

```bash
# 1. 环境初始化
make setup

# 2. 环境预检
make preflight TOOL=opencode-cli MODEL=bailian-coding-plan/qwen3.6-plus

# 3. 运行单次评测
make run-v51 TOOL=opencode-cli MODEL=bailian-coding-plan/qwen3.6-plus

# 3b. 通过 LiteLLM Proxy 运行（推荐，token 数据更精确）
make run-v51-proxy TOOL=claude-code MODEL=claude-sonnet-4

# 3c. Dry-run 模式（仅测试 prompt，不发起真实 API 调用）
make run-v51-dry TOOL=opencode-cli MODEL=bailian-coding-plan/qwen3.6-plus

# 4. 批量评测（所有默认组合）
make batch-v51

# 5. 生成报告
make report-v51                              # 最新运行的报告
make compare-v51                             # 跨 run 横向对比
make export-v51                              # 导出 CSV/JSON/Markdown
make selftest                                # schema 校验
```

## CLI 适配器与 Token 追踪

v5.1 为每个 CLI 工具提供专用适配器，支持两种 token 数据来源：

| 工具 | 原生解析方式 | Proxy 路由 | data_source |
|------|-------------|------------|-------------|
| claude-code | `--output-format json` NDJSON | `ANTHROPIC_BASE_URL` | litellm_proxy |
| gemini-cli | `step_finish` 事件 | 部分支持 | litellm_proxy |
| cursor-cli | N/A | Provider 依赖 | litellm_proxy |
| opencode-cli | `step_finish` JSONL | Provider 依赖 | litellm_proxy |

**数据优先级**: `litellm_proxy` > `native_output` > `none`
- 当 Proxy 可用时，使用 auditor.py 按时间窗口过滤 JSONL 日志，获取精确 per-stage token
- 当 Proxy 不可用时，适配器从 CLI 输出中解析 token（可能不完整）
- 若两者均不可用，该 stage 的 token 数据为 0，**不会估算或伪造**

## 模型定价与成本分析

以下价格来自各 provider 官方定价页（每 1M tokens，USD）：

| 模型 | Input | Output | Cache Read | Cache Write | 实测 ~$/AR |
|------|-------|--------|------------|-------------|------------|
| claude-sonnet-4 | $3.00 | $15.00 | $0.30 | $3.75 | ~$0.50 |
| claude-4.6-opus-high-thinking | $15.00 | $75.00 | $1.50 | $18.75 | ~$2.50 |
| gemini-3.1-pro | $1.25 | $10.00 | $0.10 | $1.50 | ~$0.40 |
| gemini-2.5-pro | $1.25 | $10.00 | $0.10 | $1.50 | ~$0.40 |
| gpt-4.1 | $2.00 | $8.00 | $0.25 | $2.50 | ~$0.35 |
| glm-5 | $0.50 | $2.00 | $0.10 | $0.50 | ~$0.35 |
| glm-4.7 | $0.50 | $2.00 | $0.10 | $0.50 | ~$0.35 |
| kimi-k2.5 | $0.50 | $2.00 | $0.10 | $0.50 | ~$0.32 |
| minimax-m2.5 | $0.50 | $2.00 | $0.10 | $0.50 | ~$0.35 |
| qwen3.5-plus | $0.50 | $2.00 | $0.10 | $0.50 | ~$0.32 |
| qwen3.6-plus | — | — | — | — | ~$0.88 |

> ~$/AR 基于实际 benchmark 遥测数据。支持 Context Caching 的模型（如 qwen3.5-plus、kimi-k2.5）
> 可节省 70%+ 的 input token 成本；不支持 Caching 的模型（如 qwen3.6-plus）成本较高。

## 并行评测

v5.1 支持同时运行多个不同模型的 benchmark，各 run 之间完全隔离：

- **Workspace 隔离**: 每个 run 使用独立的 `{run_id}_logs/` 目录
- **模型隔离**: 通过 `--model` CLI 参数指定，无全局状态共享
- **认证隔离**: opencode 使用 `~/.local/share/opencode/auth.json` 按 provider 存储
- **日志隔离**: 每个 run 输出到独立的 `_full.json` 文件

**并行运行示例**:
```bash
# 终端 1
make run-v51 TOOL=opencode-cli MODEL=bailian-coding-plan/glm-5

# 终端 2
make run-v51 TOOL=opencode-cli MODEL=bailian-coding-plan/kimi-k2.5

# 终端 3
make run-v51 TOOL=opencode-cli MODEL=bailian-coding-plan/qwen3.5-plus
```

**注意事项**:
- 所有模型共享同一个 API Key（`bailian-coding-plan`），需注意 rate limit
- 建议同时运行的模型数 ≤ 6，避免 API 限流
- 系统资源：6 个并发 benchmark 约消耗 ~8.2GB 内存（16GB 系统），已配置 4GB swap 防 OOM

## 数据完整性保障

| 保障层 | 机制 | 验证命令 |
|--------|------|----------|
| **Reconciliation** | 每完成一个 AR 后重新解析全部日志，修正 api_calls 膨胀 | 自动执行 |
| **数据合约** | `schema.py` 定义全部核心指标，报告生成前强制校验 | `make selftest` |
| **环境预检** | `preflight.py` 检查依赖、工具链、API 连通性 | `make preflight` |
| **零伪造** | dry-run 仅打印 prompt，不估算 token | `make run-v51-dry` |

## 目录结构

```
sdd-tee/
├── Makefile                    # 统一入口（所有操作通过 make 触发）
├── configs/
│   └── litellm_config.yaml     # LiteLLM Proxy 路由配置
├── specs/                      # 43 个 AR 规格文件
├── scripts/
│   ├── engine.py               # 主 benchmark 驱动 (v5.1)
│   ├── auditor.py              # LiteLLM JSONL token 审计器
│   ├── schema.py               # 数据 schema 校验
│   ├── report.py               # HTML 报告生成
│   ├── compare.py              # 跨 run 横向对比
│   ├── export.py               # CSV/JSON/Markdown 导出
│   ├── preflight.py            # 环境验证
│   ├── run_benchmark.sh        # 单次评测入口
│   ├── batch_benchmark.sh      # 批量评测入口
│   └── adapters/
│       ├── base.py             # StageRecord + BaseAdapter 基类
│       ├── claude_code.py      # Claude Code 适配器
│       ├── gemini_cli.py       # Gemini CLI 适配器
│       ├── cursor_cli.py       # Cursor CLI 适配器
│       └── opencode_cli.py     # OpenCode CLI 适配器
├── workspaces/                 # 按 run 隔离的代码工作区
└── results/
    ├── runs/v5.1/              # _full.json + 日志备份
    └── reports/v5.1/           # HTML 报告与对比看板
```

## License

MIT
