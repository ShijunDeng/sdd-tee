# SDD-TEE: Token Efficiency Evaluation Proposal

## 1. 目标项目分析

**目标仓库**: https://github.com/ShijunDeng/agentcube.git

AgentCube 是 Volcano 社区的子项目，为 Kubernetes 上的 AI Agent 工作负载提供调度和生命周期管理。

| 指标 | 数值 |
|------|------|
| 总文件数 | 275 |
| Go 代码行数 | ~17,368 |
| Python 代码行数 | ~6,889 |
| TypeScript 代码行数 | ~315 |
| YAML 配置行数 | ~10,061 |
| 主要模块 | pkg(66), docs(53), cmd(28), client-go(25), sdk-python(23) |

**核心组件**: Kubernetes CRD (AgentRuntime, CodeInterpreter), Router, WorkloadManager, CLI, Python SDK, Helm Charts

---

## 2. 方案总体架构

```
┌──────────────────────────────────────────────────────────┐
│              SDD-TEE Evaluation Pipeline                  │
│                                                          │
│  前置（一次性）:  项目技术解析 + 规范逆向生成              │
│                                                          │
├──────────────┬──────────────┬────────────────────────────┤
│   Stage 0    │   Stage 1    │        Stage 2             │
│   SDD开发    │   质量验证    │    数据汇总与报告生成       │
└──────────────┴──────────────┴────────────────────────────┘
```

### 前置工作 A: 项目技术解析 (一次性，不计入 benchmark)
- 克隆目标仓库
- 统计代码量、语言分布、模块结构
- 输出项目技术解析报告 (HTML)
- **产出可复用**，后续评测无需重新生成

### 前置工作 B: 规范逆向生成 (一次性，不计入 benchmark)
- **工具**: `spec-gen` + DeepWiki + LLM
- **步骤**:
  1. `spec-gen analyze` — 静态分析代码库，构建依赖图（无 token 消耗）
  2. `spec-gen generate` — LLM 驱动生成 OpenSpec 规范文档（消耗 token）
  3. DeepWiki 抓取架构文档作为补充参考
  4. 人工审核和完善规范文档
- **输出**: 完整的 OpenSpec 规范集（PRD、API specs、数据模型、架构设计）

### Stage 0: SDD 端到端开发 (核心 token 消耗追踪)
- **工具**: OpenSpec + 各种 AI Coding Assistant
- **对每个 AI 工具 × 模型组合**:
  1. 创建干净的工作空间
  2. 导入 Stage 1 生成的规范
  3. 运行 OpenSpec 工作流: `opsx:new` → `opsx:ff` → `opsx:apply`
  4. 记录每个阶段的 token 使用量
- **输出**: 各工具生成的代码 + token 消耗数据

### Stage 1: 质量验证 (可选 token 消耗)
- 代码结构对比 (文件数、LOC、目录结构)
- 功能点覆盖率检查
- 编译/lint 通过率
- 测试通过率（如有）

### Stage 2: 数据汇总与可视化
- 汇总 JSON/CSV 数据
- 生成对比图表 (Python matplotlib/plotly)

---

## 3. Token 追踪方案

### 3.1 通用方案: LiteLLM Proxy (推荐)

使用 LiteLLM 作为统一代理层，拦截所有 AI 工具的 API 调用：

```
AI Coding Tool → LiteLLM Proxy → Real API (OpenAI/Anthropic/etc.)
                     │
                     ▼
              Token Usage Log (SQLite/JSON)
```

**优势**:
- 工具无关，统一度量
- 精确记录 input/output/cache tokens
- 按 session/stage 分组统计

### 3.2 工具原生追踪

| 工具 | 原生追踪方式 | 精度 |
|------|------------|------|
| Claude Code | OpenTelemetry export / SDK `total_cost_usd` | 高 |
| Aider | `.aider.chat.history.md` 中的 session cost | 中 |
| Cursor | 有限的内置统计 | 低 |
| OpenCode | tokenscope 插件 | 高 |

### 3.3 推荐策略: 双轨追踪

同时使用 LiteLLM Proxy（统一口径）+ 工具原生追踪（交叉验证）

---

## 4. 测评矩阵

### 4.1 AI Coding 工具

| 工具 | 类型 | 自动化友好度 | 备注 |
|------|------|------------|------|
| Claude Code | CLI (headless) | ★★★★★ | 支持 SDK，最易自动化 |
| Aider | CLI | ★★★★★ | 纯 CLI，易脚本化 |
| OpenCode | CLI | ★★★★☆ | CLI 工具，可自动化 |
| Cursor | IDE | ★★☆☆☆ | 需要 GUI，难自动化 |

### 4.2 模型

| 模型 | 提供商 |
|------|--------|
| Claude Sonnet 4 | Anthropic |
| Claude Opus 4 | Anthropic |
| GPT-4.1 | OpenAI |
| Gemini 2.5 Pro | Google |
| DeepSeek R1 / V3 | DeepSeek |

### 4.3 输出数据格式

每次运行产出一个 JSON 文件:

```json
{
  "run_id": "uuid",
  "timestamp": "2026-03-21T10:00:00Z",
  "project": "agentcube",
  "tool": "claude-code",
  "model": "claude-sonnet-4-20250514",
  "stages": {
    "spec_generation": {
      "duration_seconds": 120,
      "input_tokens": 50000,
      "output_tokens": 15000,
      "cache_read_tokens": 0,
      "cost_usd": 0.25
    },
    "planning": {
      "duration_seconds": 60,
      "input_tokens": 30000,
      "output_tokens": 8000,
      "cache_read_tokens": 10000,
      "cost_usd": 0.12
    },
    "implementation": {
      "duration_seconds": 600,
      "input_tokens": 200000,
      "output_tokens": 80000,
      "cache_read_tokens": 50000,
      "cost_usd": 1.50
    },
    "validation": {
      "duration_seconds": 30,
      "input_tokens": 10000,
      "output_tokens": 3000,
      "cache_read_tokens": 5000,
      "cost_usd": 0.05
    }
  },
  "totals": {
    "duration_seconds": 810,
    "input_tokens": 290000,
    "output_tokens": 106000,
    "cost_usd": 1.92
  },
  "quality": {
    "files_generated": 150,
    "loc_generated": 15000,
    "compile_pass": true,
    "lint_pass": true,
    "test_pass_rate": 0.85,
    "structure_similarity": 0.78
  }
}
```

---

## 5. 自动化方案

### 5.1 整体自动化程度评估

| 阶段 | 自动化可行性 | 说明 |
|------|------------|------|
| Stage 0: 项目分析 | ★★★★★ 全自动 | 纯脚本 |
| Stage 1: 规范逆向 | ★★★★☆ 半自动 | spec-gen 自动生成，人工审核 |
| Stage 2: SDD 开发 | ★★★★☆ 高度自动 | CLI 工具可脚本化，需处理异常 |
| Stage 3: 质量验证 | ★★★★★ 全自动 | 纯脚本对比 |
| Stage 4: 数据汇总 | ★★★★★ 全自动 | Python 脚本 |

### 5.2 自动化编排

使用 Python 脚本 + Makefile 编排:

```
benchmark/
├── Makefile                    # 顶层编排
├── config.yaml                 # 测评配置（工具、模型、参数）
├── scripts/
│   ├── 00_analyze_project.sh   # Stage 0
│   ├── 01_generate_specs.sh    # Stage 1
│   ├── 02_sdd_develop.sh       # Stage 2
│   ├── 03_validate.sh          # Stage 3
│   └── 04_report.py            # Stage 4
├── specs/                      # 逆向生成的规范文档
├── workspaces/                 # 各工具的开发工作空间
│   ├── claude-code-sonnet4/
│   ├── aider-sonnet4/
│   └── ...
├── results/                    # 测评结果数据
│   ├── runs/                   # 单次运行 JSON
│   └── reports/                # 汇总报告与图表
└── PROPOSAL.md                 # 本文档
```

### 5.3 关键限制与注意事项

1. **Cursor 难以自动化**: Cursor 是 IDE，无 headless 模式，建议以手动方式进行，单独记录
2. **规范质量影响结果**: Stage 1 生成的规范质量直接影响 Stage 2，建议首轮人工审核
3. **API Rate Limits**: 并行运行多个工具时注意 API 限制
4. **成本控制**: 建议先在小模块上试运行，估算全量成本后再决定
5. **可复现性**: 每次运行记录完整的环境信息（工具版本、模型版本、时间戳）

---

## 6. 推荐执行步骤

### Phase 1: 基础设施搭建 (1-2 小时)
1. 搭建 LiteLLM Proxy 用于 token 追踪
2. 安装 OpenSpec、spec-gen、各 AI Coding 工具
3. 创建 benchmark 框架骨架

### Phase 2: 规范生成 (2-4 小时)
1. 运行 spec-gen 分析 agentcube
2. 通过 DeepWiki 获取补充文档
3. 审核和完善规范

### Phase 3: 基线测评 (每个工具×模型 1-3 小时)
1. 选定 2-3 个主力工具 + 2-3 个模型
2. 运行 SDD 全流程
3. 收集 token 数据

### Phase 4: 分析与报告 (1-2 小时)
1. 汇总数据
2. 生成对比图表
3. 撰写结论

---

## 7. 结论

**推荐方案**: 以 **Claude Code + Aider** 为主力测评工具（自动化程度最高），以 **LiteLLM Proxy** 做统一 token 追踪，使用 **spec-gen** 逆向生成 OpenSpec 规范，通过 **Python 脚本** 编排整个流程。

整个流程预计 80%+ 可自动化，仅规范审核和异常处理需要人工介入。
