# SDD-TEE — SDD Token Efficiency Evaluation

基于 **CodeSpec 7 阶段工作流** 与 **OpenSpec OPSX 工具链**的 AI Coding Assistant Token 效率评估框架。

通过将真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 拆解为 **43 个细粒度 AR（分配需求）**，
每个 AR 走完整的 SDD 流程（`/opsx:new` → `/opsx:ff` → `/opsx:apply` → `/opsx:verify` → `/opsx:archive`），
**量化 8 个阶段（ST-0~ST-7）× 5 个维度的 Token 消耗**，为 Token 提效研究提供评估基线。

## 核心演进：v3.0 Reinforced Evaluation

v3.0 引入了 **Realism Guard (现实主义护栏)** 架构，确保评测数据的真实性与代码的实质性完成度：

1.  **Session Isolation (会话隔离)**: 每个评测轮次强制清理环境，避免历史缓存干扰 Token 统计。
2.  **LOC Delta Gate (代码增量门禁)**: 实时监控每个阶段的代码产出，禁止 AI 通过“伪造存根 (Stubs)”或“空实现”来刷低 Token 消耗。
3.  **Penalty Retry (惩罚性重试)**: 一旦检测到低 LOC 或空代码产出，自动触发“惩罚性 Prompt”，强制模型重新进行实质性开发。
4.  **Cumulative Turn Summation (转录累加)**: 精确统计 Agentic Loop 中每一轮对话的累加消耗，而非仅取最后一轮。

## 评测体系

### 5 维指标体系

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
make preflight

# 3. 运行评测 (支持 v3.0 自动化编排)
make run TOOL=gemini-cli  MODEL=gemini-3.1-pro-preview
make run TOOL=opencode-cli MODEL=bailian-coding-plan/qwen3.5-plus

# 4. 采集并生成报告 (自动归档至 results/reports/v3.0/)
make collect
make report
make compare
```

## 目录结构

```
sdd-tee/
├── configs/                    # 配置文件中心
│   ├── config.yaml             # 评测配置（工具、模型、AR 列表）
│   └── litellm_config.yaml     # LiteLLM Proxy 路由配置
├── orchestration/              # 自动化编排与看护脚本
│   ├── launch_v3_group1.sh     # 并行启动任务组
│   ├── supervise_v3.sh         # 实时监控、自动补齐与数据归档
│   └── master_v3_runner.sh     # 全量自动化评测主入口
├── scripts/                    # 核心逻辑脚本
│   ├── schema.py               # 数据合约校验
│   ├── 07_sdd_tee_report.py    # 维度报告生成
│   ├── 09_collect_run_data.py  # 物理 LOC 与 Token 采集
│   ├── 11_compare_runs.py      # 跨模型横向对比报告
│   └── utils/                  # 维护与审计工具集
├── logs/                       # 统一存放评测过程日志 (.log)
├── specs/                      # 逆向生成的 OpenSpec 规范
├── workspaces/                 # 评测实时生成代码 (v1.0/v2.0/v3.0)
└── results/                    # 评测产物
    ├── runs/                   # 每次评测的 JSON 原始数据 (含 logs 备份)
    └── reports/                # HTML 维度报告与对比看板
```

## 可重入性保障

| 保障层 | 机制 | 验证命令 |
|--------|------|----------|
| **Realism Guard** | v3.0 强制 LOC 增量校验与惩罚性重试，杜绝 Stub 欺诈 | 见报告第 9 节 |
| **数据合约** | `schema.py` 定义全部 16+ 核心指标，报告生成前强制校验 | `make selftest` |
| **环境预检** | `preflight.py` 检查依赖、工具链、API 连通性 | `make preflight` |
| **自动化归档** | 脚本自动将 Raw Logs、JSON、HTML 报告同步至 Git | `git status` |

## License

MIT
