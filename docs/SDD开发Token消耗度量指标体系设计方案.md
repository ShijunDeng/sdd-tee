# SDD-TEE: Token 效率评估指标体系设计方案

> 本文档定义 SDD-TEE（SDD Token Efficiency Evaluation）的完整指标体系，
> 包括指标定义、数据采集方案、基线建立方法和预警规则。
> 与评测体系设计 (`PROPOSAL.md`) 和报告脚本 (`07_sdd_tee_report.py`) 保持一致。

---

## 一、指标体系总体架构

```
SDD Token 效率评估指标体系
├── 维度 1：阶段维度 — 按 CodeSpec 8 阶段工作流 (ST-0 ~ ST-7)
├── 维度 2：角色维度 — 人 vs AI vs 预制规范 (RT-*)
├── 维度 3：效率维度 — Token / 产出 (ET-*)
├── 维度 4：质量维度 — Token / 质量指标 (QT-*)
└── 维度 5：分布维度 — 阶段间 Token 分配 (PT-*)
```

**设计原则：**

- 每个 AR（分配需求）是度量的基本单元
- 每个阶段同时追踪 input / output / cache_read / cache_write 四类 Token
- 预制规范（前置工作生成的 spec 文档）计入 input tokens，但单独标注，不计入人工输入
- 所有指标均可按 AR 规模（S/M/L）和需求类型分层聚合

## 二、核心指标体系

### 2.1 阶段维度指标（ST-0 ~ ST-7）

CodeSpec 7 阶段工作流，通过 OpenSpec OPSX 命令驱动：

| 编码 | 阶段 | OPSX 命令 | 产物 | Token 计算 |
|------|------|-----------|------|------------|
| **ST-0** | AR 输入 | `/opsx:new` | `changes/{AR-ID}/` 目录 | Input + Output |
| **ST-1** | 需求澄清 | `/opsx:ff` → proposal | `proposal.md` | Input + Output |
| **ST-2** | Spec 增量设计 | `/opsx:ff` → specs | `delta-spec.md` | Input + Output |
| **ST-3** | Design 增量设计 | `/opsx:ff` → design | `design.md` | Input + Output |
| **ST-4** | 任务拆解 | `/opsx:ff` → tasks | `tasks.md` | Input + Output |
| **ST-5** | 开发实现 | `/opsx:apply` | 代码文件 | ∑(每个 Task 的 Token) |
| **ST-6** | 一致性验证 | `/opsx:verify` | 验证报告 | Input + Output |
| **ST-7** | 合并归档 | `/opsx:archive` | 归档 + 全量 spec 合并 | Input + Output |

> **说明：** ST-6（验证）在 ST-7（归档）之前执行，确保先验证一致性再合并到全量文档。
> 这与 OpenSpec OPSX 的 verify → archive 顺序一致。

**每阶段采集的数据字段：**

| 字段 | 说明 |
|------|------|
| `input_tokens` | 送入模型的 Token 数（含上下文） |
| `output_tokens` | 模型生成的 Token 数 |
| `cache_read_tokens` | 从 Prompt Cache 命中读取的 Token 数 |
| `cache_write_tokens` | 写入 Prompt Cache 的 Token 数 |
| `spec_context_tokens` | 其中来自预制规范文档的 Token 数（∈ input_tokens） |
| `human_input_tokens` | 其中来自人工输入的 Token 数（∈ input_tokens） |
| `iterations` | 该阶段的交互轮数 |
| `duration_seconds` | 该阶段的 wall-clock 耗时 |
| `api_calls` | API 调用次数 |

### 2.2 角色维度指标（RT-*）

| 编码 | 名称 | 计算公式 | 说明 |
|------|------|----------|------|
| **RT-AI** | AI 消耗 Token 总量 | `总 Token - RT-HUMAN - RT-SPEC` | AI Agent 自身消耗 |
| **RT-HUMAN** | 人工输入 Token 总量 | `∑(human_input_tokens)` | 人工编写的 prompt / 反馈 |
| **RT-SPEC** | 预制规范 Token 总量 | `∑(spec_context_tokens)` | 前置工作生成的 spec 文档上下文 |
| **RT-RATIO** | 人机 Token 比 | `RT-HUMAN / RT-AI` | 衡量人机协作效率 |
| **RT-ITER** | 平均迭代次数 / AR | `∑(iterations) / AR 数量` | 每个 AR 的平均交互轮数 |

**预制规范的处理规则：**

- 一次性前置工作生成的 spec 文档（`specs/*.md`）在 ST-3/ST-4/ST-5/ST-6 阶段作为 input context 注入
- 计入 `input_tokens`，但在 `spec_context_tokens` 字段中单独记录
- **不计入** RT-HUMAN（人工输入），因为这是自动化流程的一部分
- 在报告中标注为"预制规范"，与人工输入和 AI 自主消耗分开展示

### 2.3 效率维度指标（ET-*）

| 编码 | 名称 | 计算公式 | 说明 |
|------|------|----------|------|
| **ET-LOC** | Token / 代码行数 | `ST-5_total / 实际 LOC` | 每行代码的 Token 成本 |
| **ET-FILE** | Token / 文件数 | `ST-5_total / 实际文件数` | 每个文件的 Token 成本 |
| **ET-TASK** | Token / 任务数 | `ST-5_total / Task 数量` | 每个 Task 的平均 Token |
| **ET-AR** | Token / AR | `∑(ST-0~ST-7) / AR 数量` | 单个 AR 的完整 Token 消耗 |
| **ET-TIME** | Token / 小时 | `总 Token / 总耗时(h)` | Token 消耗速率 |
| **ET-COST-LOC** | 成本 / 千行代码 | `总成本 USD / (LOC / 1000)` | 每千行代码的美元成本 |

### 2.4 质量维度指标（QT-*）

| 编码 | 名称 | 计算公式 | 测量方法 | 说明 |
|------|------|----------|----------|------|
| **QT-COV** | Token / 测试覆盖率 | `ST-5_total / 覆盖率%` | Go: `go test -cover`; Python: `pytest --cov` | 每单位覆盖率的 Token 成本 |
| **QT-CONSIST** | Token / 一致性得分 | `ST-6_total / 一致性%` | 对比 delta-spec 规则与代码实现的匹配率 | 一致性验证的 Token 效率 |
| **QT-AVAIL** | Token / 代码可用率 | `ST-5_total / 可用率%` | 生成代码中可直接使用（编译通过 + 语法正确 + 逻辑合理）的比例 | 代码质量的 Token 效率 |
| **QT-BUG** | Token / Bug 数 | `ST-5_total / Bug 数` | Lint 告警 + 编译错误 + 运行时异常的总数 | 反向指标，值越高越好 |

**质量指标的自动化测量方法：**

| 指标 | Go 项目 | Python 项目 | YAML/Dockerfile |
|------|---------|-------------|-----------------|
| 编译/语法通过率 | `go build ./...` | `py_compile` | `yamllint` / `hadolint` |
| 测试覆盖率 | `go test -coverprofile` | `pytest --cov --cov-report=json` | N/A |
| Spec-Code 一致性 | 验证 API 路由 / CRD 字段与 spec 定义匹配 | 验证 CLI 参数 / SDK 方法签名与 spec 匹配 | 验证 Helm values / RBAC 规则与 spec 匹配 |
| 代码可用率 | 编译通过文件数 / 总文件数 | 语法正确文件数 / 总文件数 | 格式校验通过数 / 总文件数 |

### 2.5 阶段分布维度指标（PT-*）

| 编码 | 名称 | 计算公式 | 说明 |
|------|------|----------|------|
| **PT-DESIGN** | 设计阶段 Token 占比 | `(ST-1 + ST-2 + ST-3) / 总 Token` | 需求澄清 + Spec 设计 + Design 设计 |
| **PT-PLAN** | 规划阶段 Token 占比 | `(ST-0 + ST-4) / 总 Token` | AR 输入 + 任务拆解 |
| **PT-DEV** | 开发阶段 Token 占比 | `ST-5 / 总 Token` | 代码实现（通常为主体） |
| **PT-VERIFY** | 验证归档 Token 占比 | `(ST-6 + ST-7) / 总 Token` | 一致性验证 + 合并归档 |
| **PT-PEAK** | 峰值 Token 阶段 | `argmax(ST-0 ~ ST-7)` | 消耗最大的阶段（通常为 ST-5） |
| **PT-CACHE** | Cache 命中率 | `cache_read / input_tokens` | Prompt Cache 的有效利用率 |

**参考分布（基于行业数据）：**

| 阶段组 | 预期占比范围 | 异常阈值 |
|--------|-------------|---------|
| 设计 (ST-1~3) | 15-30% | <10% 或 >40% |
| 规划 (ST-0,4) | 5-15% | >20% |
| 开发 (ST-5) | 45-65% | >80% |
| 验证归档 (ST-6,7) | 8-18% | >25% |

## 三、基线建立方案

### 3.1 穿刺实验设计

**实验目标：** 建立 SDD 开发各阶段 Token 消耗基线

**样本设计：**
- 按 agentcube 项目拆分的 43 个 AR，覆盖 S/M/L 三种规模
- 类型覆盖：新功能（35 个）、测试（4 个）、基础设施（4 个）

**每个 AR 采集数据：**
- 元数据：AR 编号、名称、模块、语言、规模（S/M/L）、类型
- 阶段 Token：ST-0~ST-7 各阶段的 input / output / cache / duration / iterations
- 产出数据：实际 LOC、文件数、Task 数、测试覆盖率
- 质量数据：Spec-Code 一致性、代码可用率、Bug 数
- 成本数据：Token 总量、USD 成本（按模型定价计算）

### 3.2 基线计算方法

**步骤 1：按 AR 规模分层**

| 规模 | LOC 范围 | 基线 = 该层所有 AR 的平均值 |
|------|----------|---------------------------|
| S | < 500 | 平均 Token、平均 LOC、平均 Token/LOC、平均成本、平均耗时 |
| M | 500 - 2000 | 同上 |
| L | > 2000 | 同上 |

**步骤 2：建立阶段分布基线**

```
PT-DESIGN 基线 = mean((ST-1+ST-2+ST-3) / 总Token) across all ARs
PT-DEV 基线    = mean(ST-5 / 总Token) across all ARs
PT-VERIFY 基线 = mean((ST-6+ST-7) / 总Token) across all ARs
```

**步骤 3：建立效率基线**

```
ET-LOC 基线  = mean(ST-5 / LOC) across all ARs
ET-TASK 基线 = mean(ST-5 / Tasks) across all ARs
ET-TIME 基线 = mean(总Token / 耗时h) across all ARs
```

### 3.3 参考校准数据

**行业基准（2026）：**

| 来源 | 数据 |
|------|------|
| BSWEN (100M tokens tracked) | Claude Code ~78K tokens/request, 84% cache hit, 166:1 I/O ratio |
| Iterathon 2026 | Claude Sonnet $0.08/task, GPT Codex $0.24/task |
| SWE-AGI 2026 | GPT-5.3 86.4%, Claude Opus 68.2% on spec-driven construction |

**企业穿刺参考（CodeSpec 试点）：**

| 案例 | 规模 | 耗时 | 产出 | 可用率 | 备注 |
|------|------|------|------|--------|------|
| 服务集群升级 | L | 4 天 | 8K LOC, 90+ 测试 | — | 首个穿刺，全流程 SDD |
| Agent Infra 会战 | L | 9 天 (设计7+开发2) | 1.5K/2K LOC | 75% | 新人友好，边界定义影响可用率 |
| 多功能点适配 | M | — | 945 LOC, 45 UT | 88% 覆盖 | 三轮 UT 迭代 |
| 组合 API Redis | M | 5 天 | 2.1K LOC, 60+ UT | 3x 提效 | 完整 5 步 SDD |
| 实例保护完整交付 | L | 2 周 | 3K LOC (核心 1.5K), 75 文件 | 1x 提效 | 分阶段增量交付 |

**关键实践发现：**
- AI 代码可用率受 Spec/Design 文档完整度直接制约
- 边界模糊时可用率 <70%，边界清晰时可提升至 >85%
- Delta-Design 模板质量决定生成上限
- 分步验证 + 小步快跑是避免误差累积的关键策略

## 四、数据采集方案

### 4.1 双轨追踪

| 方式 | 工具 | 精度 | 数据粒度 |
|------|------|------|----------|
| **LiteLLM Proxy** | LiteLLM 统一代理 | 高 | per-request 的 input/output/cache tokens |
| **工具原生** | Claude Code OTel / Aider session cost | 中-高 | per-session 聚合 |

**推荐：** 双轨并行，LiteLLM 为主（统一口径），工具原生为辅（交叉验证）。

### 4.2 采集点与触发时机

| 采集点 | 阶段 | 触发 | 采集内容 |
|--------|------|------|----------|
| `/opsx:new` 完成 | ST-0 | 变更目录创建后 | input/output tokens, duration |
| `/opsx:ff` → proposal 完成 | ST-1 | proposal.md 生成后 | input/output/cache tokens, iterations |
| `/opsx:ff` → specs 完成 | ST-2 | delta-spec.md 生成后 | 同上 |
| `/opsx:ff` → design 完成 | ST-3 | design.md 生成后 | 同上 |
| `/opsx:ff` → tasks 完成 | ST-4 | tasks.md 生成后 | 同上 |
| `/opsx:apply` 每个 Task | ST-5 | 每个 Task 完成后 | 按 Task 粒度记录 |
| `/opsx:verify` 完成 | ST-6 | 验证报告生成后 | input/output tokens, 一致性得分 |
| `/opsx:archive` 完成 | ST-7 | 归档完成后 | input/output tokens |
| Git 统计 | — | 全流程完成后 | LOC, 文件数, diff stats |
| 测试执行 | — | 全流程完成后 | 覆盖率, 通过率, Bug 数 |

### 4.3 Token 分类标注

每条 Token 记录需标注来源类别：

```json
{
  "stage": "ST-5",
  "input_tokens": 85000,
  "output_tokens": 25000,
  "cache_read_tokens": 71400,
  "cache_write_tokens": 8500,
  "token_sources": {
    "spec_context": 12000,
    "human_prompt": 3000,
    "ai_context": 70000
  }
}
```

## 五、预警规则

| 规则 | 条件 | 级别 | 响应 |
|------|------|------|------|
| 单阶段 Token > 基线 150% | `ST-x > baseline[size] * 1.5` | 黄色 | 检查 prompt 冗余或迭代过多 |
| 总 Token > 预算 120% | `AR_total > budget * 1.2` | 红色 | 暂停评审，分析原因 |
| Token/LOC > 基线 200% | `ET-LOC > baseline * 2.0` | 异常 | 检查是否存在无效生成 |
| 代码可用率 < 75% | `QT-AVAIL < 0.75` | 质量 | 检查 Spec/Design 完整度 |
| 开发阶段占比 > 80% | `PT-DEV > 0.80` | 结构 | 设计阶段投入可能不足 |
| Cache 命中率 < 50% | `PT-CACHE < 0.50` | 效率 | 上下文管理策略需优化 |

## 六、仪表盘视图

### 视图 1：AR 需求概览

AR 编号 | 名称 | 规模 | 总 Token | 成本 | 可用率 | 一致性 | 状态/预警

### 视图 2：阶段 Token 分布

- 堆叠条形图：各阶段 Token 占比（8 色段）
- 对比基线的偏差柱状图

### 视图 3：效率分析

- 散点图：Token vs LOC（按语言着色）
- 柱状图：ET-LOC 对比基线（按 S/M/L 分组）

### 视图 4：质量关联

- 散点图：Token vs 一致性得分
- 散点图：Token vs 代码可用率

### 视图 5：Token 类型分布

- 堆叠条：Input (非缓存) / Cache Read / Output / Cache Write
- 预制规范 Token 占 Input 比例

## 七、术语表

| 术语 | 定义 |
|------|------|
| **AR** (Allocated Requirement) | 分配需求，从系统需求分解后分配到子系统/模块的功能或非功能需求，是度量的基本单元 |
| **Spec** | 结构化规格文档，定义系统"应该表现出什么行为"（What & Why） |
| **Design** | 技术设计文档，定义"用什么技术手段实现"（How） |
| **Delta-Spec** | 增量规格，用 ADDED / MODIFIED / REMOVED 标记描述本次变更对业务规则的影响 |
| **Delta-Design** | 增量设计，描述本次变更的技术方案 |
| **预制规范** | 一次性前置工作逆向生成的 OpenSpec 规范文档，在评测中作为 input context 注入 |
| **OPSX** | OpenSpec 的行动式工作流命令体系（new / ff / apply / verify / archive） |
| **CodeSpec** | 面向企业 SDD 实践的方法论，以 AR 为粒度的增量驱动 7 阶段工作流 |
| **Prompt Cache** | LLM 服务端对重复 input 前缀的缓存机制，可降低 ~75% 的 input token 成本 |
