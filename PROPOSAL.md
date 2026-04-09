# SDD-TEE: 评测体系设计文档

## 1. 目标

建立基于 **CodeSpec 7 阶段工作流 × OpenSpec OPSX 工具链** 的 Token 效率评估基线，
以真实开源项目 [agentcube](https://github.com/ShijunDeng/agentcube) 为评测对象，
量化不同 AI Coding 工具 × 模型组合在 SDD 全流程中的 Token 消耗、成本和代码质量。

### 1.1 目标项目概况

| 指标 | 数值 |
|------|------|
| 总文件数 | 275 |
| Go 代码 | 89 files / 17,368 LOC |
| Python 代码 | 41 files / 6,889 LOC |
| YAML 配置 | 33 files / 10,781 LOC |
| 核心模块 | WorkloadManager, Router, Store, PicoD, CLI, SDK, Helm |

## 2. 方法论

### 2.1 CodeSpec 7 阶段工作流

以 AR（分配需求）为基本单位，每个 AR 走完整的 7 阶段流程：

```
ST-0 AR 输入         /opsx:new         → changes/{AR-ID}/
ST-1 需求澄清        /opsx:ff          → proposal.md
ST-2 Spec 增量设计    /opsx:ff          → delta-spec.md
ST-3 Design 增量设计  /opsx:ff          → design.md
ST-4 任务拆解         /opsx:ff          → tasks.md
ST-5 开发实现         /opsx:apply       → 代码文件
ST-6 一致性验证       /opsx:verify      → 验证报告
ST-7 合并归档         /opsx:archive     → 归档 + spec 合并
```

### 2.2 AR 分解策略

采用 capability/feature 粒度，将 agentcube 拆解为 **43 个 AR**：

| 领域 | AR 数 | 示例 |
|------|-------|------|
| Go 核心 (CRD/API) | 19 | CRD 类型定义、Sandbox 创建/GC、Router JWT/Session、Store Redis/Valkey |
| Python CLI/SDK | 10 | pack/build/publish 命令、DockerService、CodeInterpreterClient |
| 基础设施 | 5 | Helm Chart、RBAC、Dockerfile、Makefile、CI/CD |
| 集成/测试/文档 | 9 | client-go、Dify 插件、Go/Python 测试、E2E 测试、文档站 |

按规模分层：S（<500 LOC）、M（500-2000 LOC）、L（>2000 LOC）

### 2.3 OpenSpec OPSX 工具链集成

实际安装并使用 `openspec` CLI 驱动 AI 工具，自动化模拟人机交互：

```bash
npm install -g @fission-ai/openspec@latest
cd workspace && openspec init
```

每个 AR 通过 OPSX 命令序列驱动：
1. `/opsx:new {AR-ID}-{feature-name}` — 创建变更脚手架
2. `/opsx:ff` — 自动生成 proposal.md → specs/ → design.md → tasks.md
3. `/opsx:apply` — AI 根据 tasks.md 逐项实现代码
4. `/opsx:verify` — 验证实现与 spec 一致性
5. `/opsx:archive` — 归档，delta 合并到全量 spec/design

## 3. 指标体系（5 维）

### 3.1 阶段维度 (ST)

| 编码 | 名称 | 计算公式 |
|------|------|----------|
| ST-0 ~ ST-7 | 各阶段 Token 消耗 | Input_Token + Output_Token |

每阶段追踪：input_tokens、output_tokens、cache_read、cache_write、iterations、duration_seconds、api_calls

### 3.2 角色维度 (RT)

| 编码 | 名称 | 说明 |
|------|------|------|
| RT-AI | AI Token 总量 | 所有 AI 调用的 Token |
| RT-HUMAN | 人工输入 Token | 人工 prompt 的 Token |
| RT-RATIO | 人机 Token 比 | RT-HUMAN / RT-AI |
| RT-ITER | 平均迭代次数 | ∑(迭代) / AR 数 |

**预制规范处理**：Spec 文档计入 input tokens，标注为"预制规范"单独统计，不计入 RT-HUMAN。

### 3.3 效率维度 (ET)

| 编码 | 名称 | 计算公式 |
|------|------|----------|
| ET-LOC | Token/代码行 | ST-5 / 代码行数 |
| ET-FILE | Token/文件 | ST-5 / 文件数 |
| ET-TASK | Token/任务 | ST-5 / Task 数 |
| ET-AR | Token/需求 | ∑(ST-0~7) / AR 数 |
| ET-TIME | Token/小时 | 总 Token / 总耗时 |

### 3.4 质量维度 (QT)

| 编码 | 名称 | 计算公式 |
|------|------|----------|
| QT-COV | Token/测试覆盖率 | ST-5 / 覆盖率% |
| QT-CONSIST | Token/一致性 | ST-6 / Spec-Code 一致性% |
| QT-AVAIL | Token/可用率 | ST-5 / 代码可用率% |
| QT-BUG | Token/Bug | ST-5 / Bug 数 (反向) |

### 3.5 阶段分布维度 (PT)

| 编码 | 名称 | 计算公式 |
|------|------|----------|
| PT-DESIGN | 设计占比 | (ST-1+ST-2+ST-3) / 总 Token |
| PT-DEV | 开发占比 | ST-5 / 总 Token |
| PT-VERIFY | 验证占比 | (ST-6+ST-7) / 总 Token |
| PT-PEAK | 峰值阶段 | max(ST-0~ST-7) |

## 4. Token 追踪方案

### 双轨追踪

| 方式 | 说明 | 精度 |
|------|------|------|
| LiteLLM Proxy | 统一代理层拦截所有 API 调用 | 高（per-request） |
| 工具原生 | Claude Code OTel / Aider session cost | 中-高 |

### 预警规则

| 规则 | 阈值 | 级别 |
|------|------|------|
| 单阶段 Token > 基线 150% | ×1.5 | 黄色 |
| 总 Token > 预算 120% | ×1.2 | 红色 |
| Token/LOC > 基线 200% | ×2.0 | 异常 |
| 代码可用率 < 75% | 0.75 | 质量 |

## 5. 基线建立

### 5.1 按规模分层

| 规模 | LOC 范围 | 基线计算 |
|------|----------|----------|
| S | <500 | 同规模 AR 平均值 |
| M | 500-2000 | 同规模 AR 平均值 |
| L | >2000 | 同规模 AR 平均值 |

### 5.2 成本预测

```
新需求 Token 预估 = 基线 × 规模系数 × 复杂度系数
项目 Token 预算 = ∑(各 AR Token 预估)
```

## 6. 参考基准

| 来源 | 数据 |
|------|------|
| BSWEN 2026 (100M tokens) | Claude Code ~78K tokens/request, 84% cache hit, 166:1 I/O |
| Iterathon 2026 | Claude Sonnet $0.08/task, GPT Codex $0.24/task |
| SWE-AGI 2026 | GPT-5.3 86.4%, Claude Opus 4.6 68.2% on spec-driven construction |

## 7. v4.0 健壮性与现实主义演进

### 7.1 核心目标
解决前三版本中存在的：指标偏低、空实现、缺乏纠错、缺乏迭代、测试不足五个系统性问题。

### 7.2 统计精度修复 (Precision Metrics)
- **Sum-of-Turns**: 统计 Agentic 循环中每一轮的增量消耗，解决累计值覆盖导致的数据偏低。
- **Physical Audit**: 最终 LOC 以 `wc -l` 物理扫描为准，不再信任模型返回的统计。
- **Safe Aggregation**: 处理所有 `0`, `0.0`, `0m0s`, `None` 异常，确保报告数据连续。

### 7.3 闭环自愈机制 (Self-Correction Loop)
- **Inner-Loop Validation**: 在 ST-5 阶段结束后立即运行 `go build` 或 `ruff`。
- **Error Feedback**: 将编译/检查失败的 Stdout 重新作为 Input 发送给模型进行修复。

### 7.4 真实性模拟 (Real-world Simulation)
- **ST-1.5 Iteration**: 强制模型对复杂 AR 进行方案二选一或细节澄清。
- **Session Reset Persistence**: 确保每轮 AR 的起始环境是"干净但包含前序代码"的，模拟真实的增量开发。

### 7.5 测试驱动增强 (TDD Specs)
- **Test Specs**: 新增 `specs/testing/` 目录，包含原 `agentcube` 的核心测试逻辑。
- **AR-Test Mapping**: 每个 AR 必须包含对应的单元测试产出，否则 QT 质量分为 0。

### 7.6 实施路径
1. 梳理测试用例规范 (`specs/test_spec.md`)。
2. 重构 `scripts/utils/recover_all_tokens.py` 为标准组件。
3. 升级 `orchestration/supervise_v4.sh` 引入纠错逻辑。

## 8. 前置工作（一次性，不计入评测）

| 前置项 | 耗时 | Token | 产出 |
|--------|------|-------|------|
| 项目技术解析 | 7s | 0 (纯脚本) | analysis.json + HTML 报告 |
| 规范逆向生成 | 194s | ~97K (估算) | 3 份 spec (298 行, 11.6KB) |
