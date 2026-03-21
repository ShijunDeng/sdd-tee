# SDD-TEE 指标体系设计方案

> 本文档定义 SDD-TEE（SDD Token Efficiency Evaluation）的完整指标体系，
> 与 `PROPOSAL.md`（评测设计）和 `07_sdd_tee_report.py`（报告生成）保持一致。

---

## 一、总体架构

```
SDD Token 效率评估指标体系
├── 维度 1：阶段维度 ST — 8 阶段工作流 (ST-0 ~ ST-7)
├── 维度 2：角色维度 RT — 人 / AI / 预制规范
├── 维度 3：效率维度 ET — Token / 产出
├── 维度 4：质量维度 QT — Token / 质量指标
└── 维度 5：分布维度 PT — 阶段间 Token 分配
```

**设计原则：**

- AR（分配需求）是度量的基本单元
- 每阶段追踪 input / output / cache_read / cache_write 四类 Token
- 预制规范计入 input tokens 但单独标注，不计入人工输入
- 所有指标可按 AR 规模（S/M/L）分层聚合

## 二、指标定义

### 2.1 阶段维度（ST）

| 编码 | 阶段 | OPSX 命令 | 产物 |
|------|------|-----------|------|
| **ST-0** | AR 输入 | `/opsx:new` | `changes/{AR-ID}/` |
| **ST-1** | 需求澄清 | `/opsx:ff` → proposal | `proposal.md` |
| **ST-2** | Spec 增量设计 | `/opsx:ff` → specs | `delta-spec.md` |
| **ST-3** | Design 增量设计 | `/opsx:ff` → design | `design.md` |
| **ST-4** | 任务拆解 | `/opsx:ff` → tasks | `tasks.md` |
| **ST-5** | 开发实现 | `/opsx:apply` | 代码文件 |
| **ST-6** | 一致性验证 | `/opsx:verify` | 验证报告 |
| **ST-7** | 合并归档 | `/opsx:archive` | 归档 + spec 合并 |

> ST-6（验证）在 ST-7（归档）之前，与 OpenSpec verify → archive 顺序一致。

**每阶段采集字段：**

| 字段 | 说明 |
|------|------|
| `input_tokens` | 送入模型的 Token 数（含上下文） |
| `output_tokens` | 模型生成的 Token 数 |
| `cache_read_tokens` | Prompt Cache 命中读取量 |
| `cache_write_tokens` | 写入 Prompt Cache 量 |
| `spec_context_tokens` | 来自预制规范的 Token 数（⊂ input_tokens） |
| `human_input_tokens` | 来自人工输入的 Token 数（⊂ input_tokens） |
| `iterations` | 交互轮数 |
| `duration_seconds` | wall-clock 耗时 |
| `api_calls` | API 调用次数 |

### 2.2 角色维度（RT）

| 编码 | 名称 | 公式 |
|------|------|------|
| **RT-AI** | AI Token 总量 | `总 Token - RT-HUMAN - RT-SPEC` |
| **RT-HUMAN** | 人工输入 Token | `∑(human_input_tokens)` |
| **RT-SPEC** | 预制规范 Token | `∑(spec_context_tokens)` |
| **RT-RATIO** | 人机 Token 比 | `RT-HUMAN / RT-AI` |
| **RT-ITER** | 平均迭代次数/AR | `∑(iterations) / AR 数` |

**预制规范处理：**
- `specs/*.md` 在 ST-3/ST-4/ST-5/ST-6 阶段注入为 input context
- 计入 `input_tokens` 和 `spec_context_tokens`，**不计入** RT-HUMAN
- 报告中标注为"预制规范"，与人工输入分开展示

### 2.3 效率维度（ET）

| 编码 | 名称 | 公式 |
|------|------|------|
| **ET-LOC** | Token/代码行 | `ST-5_total / LOC` |
| **ET-FILE** | Token/文件 | `ST-5_total / 文件数` |
| **ET-TASK** | Token/任务 | `ST-5_total / Task 数` |
| **ET-AR** | Token/AR | `∑(ST-0~7) / AR 数` |
| **ET-TIME** | Token/小时 | `总 Token / 耗时(h)` |
| **ET-COST-LOC** | 成本/千行代码 | `USD / (LOC/1000)` |

### 2.4 质量维度（QT）

| 编码 | 名称 | 公式 | 测量方法 |
|------|------|------|----------|
| **QT-COV** | Token/覆盖率 | `ST-5 / 覆盖率%` | `go test -cover` / `pytest --cov` |
| **QT-CONSIST** | Token/一致性 | `ST-6 / 一致性%` | spec 规则 vs 代码实现匹配率 |
| **QT-AVAIL** | Token/可用率 | `ST-5 / 可用率%` | 编译通过 + 语法正确的文件比例 |
| **QT-BUG** | Token/Bug | `ST-5 / Bug 数` | lint + 编译错误 + 运行异常（反向指标） |

### 2.5 分布维度（PT）

| 编码 | 名称 | 公式 | 预期范围 | 异常阈值 |
|------|------|------|----------|----------|
| **PT-DESIGN** | 设计占比 | `(ST-1+ST-2+ST-3) / 总 Token` | 15-30% | <10% 或 >40% |
| **PT-PLAN** | 规划占比 | `(ST-0+ST-4) / 总 Token` | 5-15% | >20% |
| **PT-DEV** | 开发占比 | `ST-5 / 总 Token` | 45-65% | >80% |
| **PT-VERIFY** | 验证归档占比 | `(ST-6+ST-7) / 总 Token` | 8-18% | >25% |
| **PT-PEAK** | 峰值阶段 | `argmax(ST-0~7)` | 通常 ST-5 | — |
| **PT-CACHE** | Cache 命中率 | `cache_read / input_tokens` | >70% | <50% |

## 三、基线建立

### 3.1 样本设计

基于 agentcube 项目的 43 个 AR，覆盖 S/M/L 三种规模。

每个 AR 采集：元数据、ST-0~ST-7 各阶段 Token、产出（LOC/文件/Task）、质量、成本。

### 3.2 基线计算

**按规模分层：**

| 规模 | LOC | 基线 |
|------|-----|------|
| S | <500 | 该层 AR 的均值（Token、LOC、Token/LOC、成本、耗时） |
| M | 500-2000 | 同上 |
| L | >2000 | 同上 |

**阶段分布基线：**

```
PT-DESIGN = mean((ST-1+ST-2+ST-3) / 总Token)
PT-DEV    = mean(ST-5 / 总Token)
PT-VERIFY = mean((ST-6+ST-7) / 总Token)
```

**效率基线：**

```
ET-LOC  = mean(ST-5 / LOC)
ET-TASK = mean(ST-5 / Tasks)
ET-TIME = mean(总Token / 耗时h)
```

### 3.3 行业参考基准（2026）

| 来源 | 数据 |
|------|------|
| BSWEN (100M tokens) | Claude Code ~78K tokens/request, 84% cache hit, 166:1 I/O ratio |
| Iterathon 2026 | Claude Sonnet $0.08/task, GPT Codex $0.24/task |
| SWE-AGI 2026 | GPT-5.3 86.4%, Claude Opus 68.2% on spec-driven construction |

## 四、数据采集

### 4.1 双轨追踪

| 方式 | 工具 | 精度 |
|------|------|------|
| **LiteLLM Proxy** | 统一代理拦截 | 高（per-request） |
| **工具原生** | Claude Code OTel / Aider session cost / Cursor CLI (受限) | 中-高 |

### 4.2 Token 记录格式

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

| 条件 | 级别 | 响应 |
|------|------|------|
| 单阶段 Token > 基线 150% | 黄色 | 检查 prompt 冗余或迭代过多 |
| 总 Token > 预算 120% | 红色 | 暂停分析原因 |
| Token/LOC > 基线 200% | 异常 | 检查无效生成 |
| 代码可用率 < 75% | 质量 | 检查 Spec 完整度 |
| 开发占比 > 80% | 结构 | 设计投入可能不足 |
| Cache 命中率 < 50% | 效率 | 上下文策略需优化 |

## 六、报告视图

| 视图 | 内容 |
|------|------|
| AR 概览 | 编号、规模、Token、成本、可用率、一致性、预警状态 |
| 阶段分布 | 堆叠条形图（8 阶段占比）+ 基线偏差 |
| 效率分析 | 散点图 Token vs LOC + 柱状图 ET-LOC vs 基线 |
| 质量关联 | 散点图 Token vs 一致性、Token vs 可用率 |
| Token 类型 | 堆叠条 Input/Cache Read/Output/Cache Write + 预制规范占比 |

## 七、术语

| 术语 | 定义 |
|------|------|
| **AR** | 分配需求（Allocated Requirement），评测的基本度量单元 |
| **预制规范** | 前置工作逆向生成的 spec 文档，评测中作为 input context 注入 |
| **OPSX** | OpenSpec 工作流命令（new / ff / apply / verify / archive） |
| **Prompt Cache** | LLM 服务端缓存重复 input 前缀，降低 ~75% input token 成本 |
