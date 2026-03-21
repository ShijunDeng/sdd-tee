# SDD-TEE 项目上下文快照

> 生成时间: 2026-03-22T05:30:00Z
> 最新 commit: `7eed0eb Add opencode-cli GLM-5 evaluation with UT support`
> 分支: main | 远端: github.com:ShijunDeng/sdd-tee.git

---

## 1. 项目定位

SDD-TEE (SDD Token Efficiency Evaluation) — 基于 **CodeSpec 7 阶段工作流 × OpenSpec OPSX** 的 AI Coding Assistant Token 效率评估框架。

目标：将真实项目 [agentcube](https://github.com/ShijunDeng/agentcube.git) 拆解为 43 个 AR，用 4 种 CLI 工具分别走完 SDD 全流程，量化 Token 消耗，建立基线。

## 2. 核心任务文件

- **`task.md`** — 原始需求（不提交到 git）
- **`next.md`** — 当前/下一步任务指令
- **`docs/SDD开发Token消耗度量指标体系设计方案.md`** — 5 维指标体系设计方案
- **`config.yaml`** — 评测配置（工具、模型、AR 列表、预警阈值）
- **`PROPOSAL.md`** — v2 评测体系设计文档

## 3. 当前工程状态

### 已完成

| 项目 | 状态 | 说明 |
|------|------|------|
| 项目技术解析 | ✅ | `scripts/01_analyze_project.sh` + `scripts/06_project_report.py` |
| 规范逆向生成 | ✅ | `specs/` 目录，10 capabilities × (spec.md + design.md)，共 22 文件 4250 行 |
| 评测体系设计 | ✅ | 8 阶段(ST-0~ST-7) × 5 维(Stage/Role/Efficiency/Quality/Distribution) × 16 指标 |
| 数据合约层 | ✅ | `scripts/schema.py` — Single Source of Truth |
| 环境预检 | ✅ | `scripts/preflight.py` — 7 维检查，43 项通过 |
| Mock 报告 | ✅ | `scripts/07_sdd_tee_report.py --mock` → 10 节 HTML |
| 4 工具适配 | ✅ | cursor-cli / claude-code / gemini-cli / opencode-cli 全部适配 |
| 跨轮对比报告 | ✅ | `scripts/11_compare_runs.py` → 7 节对比 HTML |
| 可重入性保障 | ✅ | preflight + schema + selftest + requirements.txt |

### 已完成的评测轮次

| # | 工具 | 模型 | Run ID | Tokens | 文件 | LOC | 耗时 | 成本 |
|---|------|------|--------|--------|------|-----|------|------|
| 1 | cursor-cli | claude-4.6-opus-high-thinking | `..._20260321T070313Z` | 785,774 | 132 | 18,982 | 17m37s | $17.12 |
| 2 | cursor-cli | claude-4.6-opus-high-thinking | `..._20260321T090515Z` | 896,885 | 174 | 19,115 | 93m10s | $19.99 |
| 3 | opencode-cli | bailian-coding-plan/glm-5 | `..._20260321T114208Z` | 852,964 | 124 (含22个UT) | 18,099 | 105m26s | $18.83 |

> 轮次 1 是前一个会话手动执行的结果；轮次 2、3 是本会话通过 `make run` 自动执行的结果。
> 轮次 3 的 prompt 已更新为包含单元测试(UT)要求。

### 待执行（下一步）

| 项目 | 命令 | 说明 |
|------|------|------|
| Claude Code 评测 | `make run TOOL=claude-code MODEL=claude-sonnet-4-20250514` | Claude Code 实际评测 |
| Gemini CLI 评测 | `make run TOOL=gemini-cli MODEL=gemini-2.5-pro` | Gemini CLI 实际评测 |
| 更多 OpenCode 模型 | `make run TOOL=opencode-cli MODEL=bailian-coding-plan/qwen3-coder-plus` | 其他模型对比 |
| 跨轮对比 | `make compare` | 所有轮次完成后生成横向对比 |

## 4. 文件结构

```
/home/dsj/benchmark/
├── config.yaml                     # 评测配置（4 工具、6 模型、8 阶段、预警阈值）
├── Makefile                        # 评测编排（setup/preflight/run/collect/report/compare/selftest/eval-all）
├── PROPOSAL.md                     # v2 评测体系设计
├── README.md                       # 项目说明
├── requirements.txt                # Python 依赖
├── litellm_config.yaml             # LiteLLM Proxy 配置
├── task.md                         # 原始需求（不提交）
├── next.md                         # 当前/下一步任务指令
├── CONTEXT.md                      # ← 本文件（上下文快照）
├── docs/
│   └── SDD开发Token消耗度量指标体系设计方案.md
├── scripts/
│   ├── 01_analyze_project.sh       # 项目静态分析
│   ├── 02_generate_specs.sh        # 规范生成
│   ├── 03_sdd_develop.sh           # ★ 统一 SDD 评测执行器（4 CLI 工具适配器）
│   ├── 04_validate.py              # 代码质量验证
│   ├── 05_aggregate.py             # 数据聚合
│   ├── 06_project_report.py        # 项目技术解析报告
│   ├── 07_sdd_tee_report.py        # ★ 10 节 5 维 HTML 报告生成（含 43 AR 定义、mock 数据）
│   ├── 08_run_report.py            # 单轮运行报告（旧）
│   ├── 09_collect_run_data.py      # ★ Token 精确采集（litellm.token_counter）
│   ├── 10_litellm_runner.py        # LiteLLM 直连评测执行器
│   ├── 11_compare_runs.py          # ★ 跨轮次对比报告
│   ├── schema.py                   # ★ 数据合约（Single Source of Truth）
│   └── preflight.py                # ★ 环境预检（7 维 43 项）
├── specs/                          # OpenSpec 规范（10 capability × 2 文件）
│   ├── project.md
│   ├── sandbox-orchestration/{spec,design}.md
│   ├── session-routing/{spec,design}.md
│   ├── code-execution/{spec,design}.md
│   ├── session-store/{spec,design}.md
│   ├── idle-cleanup/{spec,design}.md
│   ├── cli-toolkit/{spec,design}.md
│   ├── python-sdk/{spec,design}.md
│   ├── deployment/{spec,design}.md
│   ├── ci-cd/{spec,design}.md
│   └── integrations/{spec,design}.md
├── workspaces/
│   ├── cursor-cli_claude-4.6-opus-high-thinking_20260321T070313Z/   # 轮次1
│   ├── cursor-cli_claude-4.6-opus-high-thinking_20260321T090515Z/   # 轮次2
│   └── opencode-cli_bailian-coding-plan_glm-5_20260321T114208Z/     # 轮次3（含UT）
└── results/
    ├── runs/
    │   ├── cursor-cli_..._20260321T070313Z{.json,_full.json,_validation.json}
    │   ├── cursor-cli_..._20260321T090515Z{.json,_full.json,_logs/}
    │   └── opencode-cli_..._20260321T114208Z{.json,_full.json,_logs/}
    └── reports/
        ├── sdd_tee_report.html           # Mock 数据标准报告
        ├── sdd_tee_report.json           # Mock 数据 JSON
        ├── compare_report.html           # 跨轮对比报告（3 轮次）
        ├── project_analysis_report.html  # 项目技术解析
        ├── cursor-cli_..._20260321T070313Z_report.html
        ├── cursor-cli_..._20260321T090515Z_report.html
        └── opencode-cli_..._20260321T114208Z_report.html
```

## 5. CLI 工具环境

| 工具 | 路径 | 非交互模式 |
|------|------|------------|
| cursor | `/root/.local/bin/cursor` | `cursor agent --trust "prompt"` |
| claude | `/root/.nvm/.../bin/claude` | `claude -p "prompt" --print --output-format json --dangerously-skip-permissions` |
| gemini | `/root/.nvm/.../bin/gemini` | `gemini -p "prompt" --yolo --output-format json` |
| opencode | `/root/.opencode/bin/opencode` | `opencode run --model <model> --format json --dir <dir> "prompt" < /dev/null` |

### 模型

- Cursor CLI: claude-4.6-opus-high-thinking（当前环境默认）
- Claude Code: claude-sonnet-4-20250514 / claude-opus-4-20250514
- Gemini CLI: gemini-2.5-pro（通过 Google OAuth 认证，~/.gemini/oauth_creds.json）
- OpenCode CLI:
  - opencode/big-pickle, opencode/gpt-5-nano 等内置模型
  - bailian-coding-plan/glm-5, bailian-coding-plan/kimi-k2.5 等（阿里百炼 Coding Plan）
  - litellm-proxy/*（需启动 LiteLLM Proxy）

### API Key / 认证状态

- ANTHROPIC_API_KEY: 未设为环境变量（Claude Code 通过自身认证）
- Gemini: OAuth 认证（~/.gemini/oauth_creds.json）
- OpenCode bailian-coding-plan: API Key 已配置在 `~/.config/opencode/config.json`
- OpenCode litellm-proxy: 需 `make proxy` 启动本地代理（端口 4000）
- GitHub CLI: 已认证

## 6. 关键设计决策

1. **Spec 是预制规范**：计入 input tokens，标注为 RT-SPEC，不算 RT-HUMAN
2. **Cursor CLI 无法直接获取 token**：用 content-based estimation（litellm.token_counter）+ SDD 阶段比例模型分配
3. **Claude Code 可通过 LiteLLM Proxy 精确追踪**：设置 `ANTHROPIC_BASE_URL=http://localhost:4000/v1`
4. **43 AR 分 4 轮执行**：每轮 10-11 个 AR，3 个 phase（Planning/Implementation/Verify）
5. **schema.py 是 Single Source of Truth**：8 stages × 9 fields × 16 metrics × 10 HTML sections × 6 warning rules
6. **模型名中的 `/` 自动转 `_`**：`03_sdd_develop.sh` 中 `MODEL_SAFE="${MODEL//\//_}"` 避免路径问题
7. **opencode run 必须 `< /dev/null`**：否则会因等待 stdin 而挂起
8. **cursor agent 必须 `--trust`**：新 workspace 需要信任标记
9. **所有路径使用绝对路径**：`PROJECT_ROOT="$(pwd)"` → LOG_DIR/WORKSPACE/RESULTS_DIR 全部基于绝对路径，避免 `cd` 后相对路径失效

## 7. 已修复的 Bug（本会话）

| Bug | 原因 | 修复 |
|-----|------|------|
| cursor agent 子进程 0 秒完成 | 新 workspace 缺少 `--trust` 标记 | 添加 `--trust` 参数 |
| cursor agent 日志文件为空 | `cd $WORKSPACE` 后 LOG_DIR 相对路径失效 | 所有路径改为绝对路径 |
| 结果 JSON 写入 `results/results/runs/` | Python 代码中 `os.path.dirname` 层数错误 | 使用 `__RESULTS_DIR` 环境变量 |
| opencode run 永远挂起 | 等待 stdin 输入 | 添加 `< /dev/null` |
| RUN_ID 中 `/` 创建子目录 | 模型名 `bailian-coding-plan/glm-5` 含 `/` | `MODEL_SAFE="${MODEL//\//_}"` |

## 8. Git 提交历史

```
7eed0eb Add opencode-cli GLM-5 evaluation with UT support
b895259 Fix cursor-cli runner and add second evaluation run
7cf8726 Add project context snapshot for session recovery
d207b7c Add 4-tool CLI support and cross-run comparison report
fb44c29 Add reentrant evaluation framework: schema contract + preflight + selftest
4854da8 Upgrade evaluation to 10-section 5-dimension standard with LiteLLM Proxy
4249791 Restructure specs to OpenSpec capability-based format
84e4858 Regenerate specs from source code (298→1906 lines)
03a69d5 Trim metrics doc to SDD-TEE scope only
9fed4c8 Run 1: Cursor CLI + claude-4.6-opus-high-thinking evaluation
```

## 9. 恢复步骤

```bash
cd /home/dsj/benchmark
git pull origin main          # 同步最新代码
make setup                    # 安装依赖（如果新环境）
make preflight                # 环境预检
cat CONTEXT.md                # 阅读本文件恢复上下文
```

## 10. 常用命令速查

```bash
# 单工具评测（完整流程）
make run TOOL=opencode-cli MODEL=bailian-coding-plan/glm-5
make collect && make report && make selftest

# Cursor CLI 评测
make run TOOL=cursor-cli MODEL=claude-4.6-opus-high-thinking

# Claude Code 评测
make run TOOL=claude-code MODEL=claude-sonnet-4-20250514

# Gemini CLI 评测
make run TOOL=gemini-cli MODEL=gemini-2.5-pro

# 跨轮对比
make compare

# Mock 报告预览
make mock

# 全部 4 工具顺序评测
make eval-all

# LiteLLM Proxy 精确追踪
make proxy &
make proxy-run MODEL=anthropic/claude-sonnet-4-20250514

# 环境预检（指定工具）
make preflight TOOL=opencode-cli MODEL=bailian-coding-plan/glm-5
```
