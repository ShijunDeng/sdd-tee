# SDD-TEE — SDD Token Efficiency Evaluation

基于 **CodeSpec 7 阶段工作流** 与 **OpenSpec OPSX 工具链**的 AI Coding Assistant Token 效率评估框架。

通过将真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 拆解为 **43 个细粒度 AR（分配需求）**，
每个 AR 走完整的 SDD 流程（`/opsx:new` → `/opsx:ff` → `/opsx:apply` → `/opsx:verify` → `/opsx:archive`），
**量化 8 个阶段（ST-0~ST-7）× 5 个维度的 Token 消耗**，为 Token 提效研究提供评估基线。

## 评测体系

### 5 维指标体系

| 维度 | 编码 | 指标示例 |
|------|------|----------|
| 阶段维度 | ST-0 ~ ST-7 | 各阶段 Input/Output/Cache Tokens、迭代数、耗时 |
| 角色维度 | RT-AI / RT-HUMAN | AI Token、人工输入 Token、人机比、预制规范（单独标注） |
| 效率维度 | ET-LOC / ET-FILE / ET-TASK | Token/LOC、Token/File、Token/Task、Token/AR、Token/h |
| 质量维度 | QT-COV / QT-CONSIST | Token/覆盖率、Token/一致性、Token/可用率、Token/Bug |
| 分布维度 | PT-DESIGN / PT-DEV | 设计/开发/验证阶段占比、峰值阶段 |

### CodeSpec 7 阶段 × OpenSpec OPSX 对齐

```
ST-0  /opsx:new     → 变更目录脚手架
ST-1  /opsx:ff      → proposal.md       (需求澄清)
ST-2  /opsx:ff      → delta-spec.md     (Spec 增量设计)
ST-3  /opsx:ff      → design.md         (Design 增量设计)
ST-4  /opsx:ff      → tasks.md          (任务拆解)
ST-5  /opsx:apply   → 代码文件           (开发实现)
ST-6  /opsx:verify  → 验证报告           (一致性验证)
ST-7  /opsx:archive → 归档 + spec 合并   (合并归档)
```

## 前置工作（一次性）

以下为一次性前置准备，成果可在所有评测中复用，Token/耗时不计入评测基线。

| 前置项 | 产出 |
|--------|------|
| 项目技术解析 | [`results/reports/project_analysis_report.html`](results/reports/project_analysis_report.html) |
| 规范逆向生成 | `specs/` 目录（10 个 capability，22 份 OpenSpec 规范） |

## 快速开始

```bash
# 1. 环境初始化（安装依赖）
make setup

# 2. 环境预检（验证工具链、config、specs 完整性）
make preflight

# 3. Mock 报告（预览报告格式 + schema 自检）
make mock

# 4. 运行评测（4 种 CLI 工具 × 任意模型）
make run TOOL=cursor-cli  MODEL=claude-4.6-opus-high-thinking
make run TOOL=claude-code MODEL=claude-sonnet-4-20250514
make run TOOL=gemini-cli  MODEL=gemini-2.5-pro
make run TOOL=opencode-cli MODEL=opencode/big-pickle

# 5. 采集 Token 数据
make collect

# 6. 生成 10 节 5 维报告（自动 schema 校验）
make report

# 7. 自检：验证报告覆盖 design doc 全部指标
make selftest

# 8. 跨轮次对比报告
make compare

# 完整管线（一键）
make all TOOL=cursor-cli MODEL=claude-4.6-opus-high-thinking

# 全部 4 种工具顺序评测 + 对比
make eval-all
```

### LiteLLM Proxy（精确 per-request Token 追踪）

```bash
export ANTHROPIC_API_KEY=sk-...
make proxy &          # 启动代理 (localhost:4000)
make proxy-run MODEL=anthropic/claude-sonnet-4-20250514
make report && make selftest
```

## 目录结构

```
sdd-tee/
├── config.yaml                 # 评测配置（工具、模型、AR 列表）
├── Makefile                    # 评测编排
├── PROPOSAL.md                 # v2 评测体系设计文档
├── scripts/
│   ├── schema.py               # 数据合约（Single Source of Truth，关联指标体系 doc）
│   ├── preflight.py            # 环境预检（7 维：依赖/工具链/config/specs/脚本/工具/代理）
│   ├── 04_validate.py          # 代码质量验证（Go build/py_compile/YAML syntax）
│   ├── 07_sdd_tee_report.py    # 报告生成（10 节 5 维，内置 schema 校验）
│   ├── 09_collect_run_data.py  # Token 采集（litellm.token_counter 精确计数）
│   ├── 10_litellm_runner.py    # LiteLLM 评测执行器（per-request Token 追踪）
│   └── 11_compare_runs.py      # 跨轮次对比报告（Tool × Model 横向比较）
├── specs/                      # 逆向生成的 OpenSpec 规范（capability-based，一次性产出）
│   ├── project.md              # 项目上下文（技术栈、架构、约定）
│   ├── {capability}/spec.md    # 需求规范（SHALL/MUST + GIVEN/WHEN/THEN 场景）
│   └── {capability}/design.md  # 技术设计（类型定义、接口、常量、路由）
├── workspaces/                 # 各评测轮次的生成代码
└── results/
    ├── project_analysis/       # 项目分析原始数据
    ├── runs/                   # 每次评测的 JSON 原始数据
    └── reports/                # HTML 报告与图表
```

## 可重入性保障

| 保障层 | 机制 | 验证命令 |
|--------|------|----------|
| **数据合约** | `schema.py` 定义全部 8 阶段 × 9 字段 × 16 指标，report 生成前自动校验 | `make selftest` |
| **环境预检** | `preflight.py` 检查 7 维：依赖/工具链/config/specs/脚本/编码工具/代理 | `make preflight` |
| **指标完整性** | 所有指标 ID 与 `docs/SDD开发Token消耗度量指标体系设计方案.md` 一一对应 | `python3 scripts/schema.py <data.json>` |
| **报告完整性** | HTML 渲染后验证 10 节标题 + 17 个必需关键词 | `python3 scripts/schema.py <data.json> <report.html>` |
| **预警完整性** | 6 条预警规则全部实现（STAGE-BUDGET/TOTAL-BUDGET/ET-LOC/USABILITY/DEV-SKEW/CACHE-LOW） | 报告第 9 节 |
| **依赖声明** | `requirements.txt` 锁定 Python 依赖 | `make setup` |
| **工具无关** | 同一管线支持 cursor-cli / claude-code / gemini-cli / opencode-cli，只需 `TOOL=xxx MODEL=xxx` | `make run TOOL=...` |
| **跨轮对比** | `11_compare_runs.py` 自动扫描全部 *_full.json，生成横向对比报告 | `make compare` |

## Token 追踪

| 方式 | 说明 |
|------|------|
| LiteLLM Proxy | 统一代理层拦截所有 API 调用，精确 per-request 记录 |
| 工具原生 | Claude Code (JSON usage) / Gemini CLI (JSON output) / OpenCode (stats) / Cursor CLI (content-based estimation) |
| 预制规范 | Spec 文档计入 input tokens，标注为"预制规范"单独统计 |

## 参考基准

| 来源 | 数据 |
|------|------|
| BSWEN 2026 (100M tokens tracked) | Claude Code ~78K tokens/request, 84% cache, 166:1 I/O |
| Iterathon 2026 | Claude Sonnet $0.08/task, Gemini $0.15/task |
| SWE-AGI 2026 | Frontier models 68-86% on spec-driven construction |

## License

MIT
