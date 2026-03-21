# SDD开发Token消耗度量指标体系设计方案

## 一、指标体系总体架构

```
SDD Token消耗度量体系
├── 维度1：阶段维度（按7阶段工作流）
├── 维度2：角色维度（人 vs AI）
├── 维度3：类型维度（输入Token vs 输出Token）
├── 维度4：效率维度（Token/产出）
└── 维度5：质量维度（Token/质量指标）
```

## 二、核心指标体系

### 2.1 阶段级Token消耗指标（核心）

| 指标编码 | 指标名称 | 计算公式 | 数据来源 | 基线目标 |
|---------|---------|---------|---------|---------|
| **ST-0** | AR输入阶段Token消耗 | `Input_Token + Output_Token` | Agent日志 | 待建立 |
| **ST-1** | 需求澄清阶段Token消耗 | `Proposal_Input + Proposal_Output` | proposal.md生成日志 | 待建立 |
| **ST-2** | Spec增量设计Token消耗 | `DeltaSpec_Input + DeltaSpec_Output` | delta-spec.md生成日志 | 待建立 |
| **ST-3** | Design增量设计Token消耗 | `DeltaDesign_Input + DeltaDesign_Output` | delta-design.md生成日志 | 待建立 |
| **ST-4** | 任务拆解Token消耗 | `Tasks_Input + Tasks_Output` | tasks.md生成日志 | 待建立 |
| **ST-5** | 开发实现阶段Token消耗 | `∑(每个Task的Token消耗)` | 代码生成日志 | 待建立 |
| **ST-6** | 合并归档阶段Token消耗 | `Merge_Input + Merge_Output` | 文档合并日志 | 待建立 |
| **ST-7** | 一致性验证Token消耗 | `Verify_Input + Verify_Output` | 验证报告生成日志 | 待建立 |

### 2.2 角色维度Token消耗指标

| 指标编码 | 指标名称 | 计算公式 | 说明 |
|---------|---------|---------|------|
| **RT-AI** | AI消耗Token总量 | `∑(所有AI调用的Token)` | AI Agent调用的总Token |
| **RT-HUMAN** | 人类输入Token总量 | `∑(人类Prompt的Token)` | 人工输入的Token |
| **RT-RATIO** | 人机Token比 | `RT-HUMAN / RT-AI` | 衡量人机协作效率 |
| **RT-ITER** | 平均迭代次数 | `∑(迭代次数) / 需求数` | 每个需求的平均交互轮数 |

### 2.3 效率维度Token消耗指标

| 指标编码 | 指标名称 | 计算公式 | 说明 |
|---------|---------|---------|------|
| **ET-LOC** | Token/代码行数 | `ST-5 / 代码总行数` | 每行代码的Token成本 |
| **ET-FILE** | Token/文件数 | `ST-5 / 变更文件数` | 每个文件的Token成本 |
| **ET-TASK** | Token/任务数 | `ST-5 / Task数量` | 每个Task的平均Token |
| **ET-AR** | Token/需求（AR） | `∑(ST-0~ST-7) / AR数量` | 单个需求的完整Token消耗 |
| **ET-TIME** | Token/小时 | `总Token / 总开发耗时` | Token消耗速率 |

### 2.4 质量维度Token消耗指标

| 指标编码 | 指标名称 | 计算公式 | 说明 |
|---------|---------|---------|------|
| **QT-COV** | Token/测试覆盖率 | `ST-5 / 单元测试覆盖率%` | 每单位覆盖率的Token成本 |
| **QT-CONSIST** | Token/一致性得分 | `ST-7 / Spec-Code一致性%` | 一致性验证的Token效率 |
| **QT-AVAIL** | Token/代码可用率 | `ST-5 / AI代码可用率%` | 生成代码质量的Token效率 |
| **QT-BUG** | Token/Bug数 | `ST-5 / 发现Bug数` | 每个Bug的Token成本（反向指标） |

### 2.5 阶段间Token分布指标

| 指标编码 | 指标名称 | 计算公式 | 说明 |
|---------|---------|---------|------|
| **PT-DESIGN** | 设计阶段Token占比 | `(ST-1+ST-2+ST-3) / 总Token` | 设计阶段Token消耗比例 |
| **PT-DEV** | 开发阶段Token占比 | `ST-5 / 总Token` | 开发阶段Token消耗比例 |
| **PT-VERIFY** | 验证阶段Token占比 | `(ST-6+ST-7) / 总Token` | 验证阶段Token消耗比例 |
| **PT-PEAK** | 峰值Token阶段 | `max(ST-0~ST-7)` | Token消耗最大的阶段 |

## 三、基线建立方案

### 3.1 穿刺实验设计

**实验目标：** 建立SDD开发各阶段Token消耗基线

**实验样本选择：**
- 选择3-5个不同复杂度的实际需求（AR）
- 覆盖不同类型：新功能开发、Bug修复、重构、性能优化
- 记录需求规模：预估代码行数、变更文件数、复杂度等级

**数据采集维度：**

每个AR需求采集：
- 需求元数据（AR编号、需求类型、预估规模、预估代码行数、预估变更文件数）
- 阶段Token消耗（ST-0~ST-7 各阶段Input/Output Token、各阶段耗时、各阶段迭代次数）
- 产出数据（实际代码行数、实际变更文件数、Task数量、单元测试覆盖率、Spec-Code一致性得分、AI代码可用率）
- 成本数据（Token总消耗、Token成本、人力成本）

### 3.2 基线计算方法

**步骤1：按需求规模分层统计**
- 小型需求（<500行代码）：Token消耗基线 = 平均值
- 中型需求（500-2000行代码）：Token消耗基线 = 平均值
- 大型需求（>2000行代码）：Token消耗基线 = 平均值

**步骤2：按需求类型分层统计**
- 新功能开发：Token消耗基线 = 平均值
- Bug修复：Token消耗基线 = 平均值
- 重构：Token消耗基线 = 平均值
- 性能优化：Token消耗基线 = 平均值

**步骤3：建立阶段分布基线**
- 设计阶段占比基线 = (ST-1+ST-2+ST-3) / 总Token 的平均值
- 开发阶段占比基线 = ST-5 / 总Token 的平均值
- 验证阶段占比基线 = (ST-6+ST-7) / 总Token 的平均值

**步骤4：建立效率基线**
- Token/代码行数基线 = ST-5 / 代码行数 的平均值
- Token/任务数基线 = ST-5 / Task数量 的平均值
- Token/小时基线 = 总Token / 总耗时 的平均值

## 四、数据采集实施方案

### 4.1 技术实现方案

**方案A：Agent日志自动采集（推荐）**
```python
# 伪代码示例
class TokenTracker:
    def track_stage(self, stage_name, input_tokens, output_tokens, duration):
        record = {
            'stage': stage_name,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': input_tokens + output_tokens,
            'duration': duration,
            'timestamp': datetime.now()
        }
        self.save_to_database(record)
```

**方案B：手动记录表单**
- 创建Excel/在线表格模板
- 每个阶段完成后手动填写Token消耗数据
- 适合初期快速验证

### 4.2 数据采集点

| 采集点 | 采集内容 | 采集方式 |
|-------|---------|---------|
| **Proposal生成** | ST-1 Token消耗 | Agent日志 |
| **Delta-Spec生成** | ST-2 Token消耗 | Agent日志 |
| **Delta-Design生成** | ST-3 Token消耗 | Agent日志 |
| **Tasks拆解** | ST-4 Token消耗 | Agent日志 |
| **代码生成** | ST-5 Token消耗（按Task） | Agent日志 |
| **文档合并** | ST-6 Token消耗 | Agent日志 |
| **一致性验证** | ST-7 Token消耗 | Agent日志 |
| **代码统计** | LOC、文件数 | Git/代码分析工具 |
| **质量指标** | 覆盖率、一致性 | 测试工具/验证工具 |

## 五、指标应用场景

### 5.1 成本估算
- 新需求Token成本预测 = 基线 × 需求规模系数 × 复杂度系数
- 项目总Token预算 = ∑(各需求Token成本)

### 5.2 效率优化
- 识别Token消耗异常高的阶段（如ST-5占比>80%）
- 分析高Token消耗的原因（Prompt冗余、迭代次数多、生成内容质量低）
- 优化Prompt策略，降低Token消耗

### 5.3 质量评估
- 对比不同需求的Token/质量指标
- 识别高Token低质量的异常需求
- 调整设计模板或Prompt策略

### 5.4 进度跟踪
- 实时监控各阶段Token消耗进度
- 预警Token消耗超预算的需求
- 动态调整资源分配

## 六、仪表盘设计建议

### 6.1 核心视图

**视图1：需求概览**
- AR编号 | 需求类型 | 总Token | 预算Token | 进度 | 状态

**视图2：阶段分布**
- 饼图：各阶段Token占比
- 趋势图：Token消耗随时间变化

**视图3：效率分析**
- 散点图：Token vs 代码行数
- 柱状图：Token/LOC 对比基线

**视图4：质量关联**
- 散点图：Token vs 测试覆盖率
- 散点图：Token vs 一致性得分

### 6.2 预警规则

- 单阶段Token消耗超过基线150% → 黄色预警
- 总Token消耗超过预算120% → 红色预警
- Token/LOC超过基线200% → 异常标记
- Token/质量指标异常 → 质量预警

## 七、实施路线图

### 阶段1：基线建立（2-4周）
- 选择3-5个穿刺需求
- 完成全流程Token数据采集
- 计算初步基线值

### 阶段2：指标验证（2周）
- 用新需求验证基线准确性
- 调整指标定义和计算方法
- 优化数据采集流程

### 阶段3：体系固化（1周）
- 固化指标定义和采集流程
- 建立自动化采集工具
- 生成基线报告

### 阶段4：持续优化（长期）
- 定期更新基线（每季度）
- 识别优化机会
- 持续改进SDD流程

## 八、说明

原始需求RR: raw requirement，来自公司内、外部客户的、关于公司产品与解决方案的、需要项目SA或者需求分析团队（RAT）分析评审后作出决定的所有需求。
特性FE: feature ，描述解决方案为支撑“客户问题（PB）”所具备的重大能力。系统特性是解决方案的主要卖点（销售亮点）集合，每条特性都是满足客户特定商业价值诉求的端到端解决方案。
初始需求IR: initial requirement，原始需求RR经过RAT分析后，站在内外部客户/市场角度，以准确的语言（完整的背景、标准的格式）重新描述的需求。
系统需求SR: system requirement，支撑特性FE所需要支持的具体需求，是系统对外呈现的可测试的全部功能用例或非功能描述，功能性需求需要按功能来分类组织。
分配需求AR: allocated requirement，根据“系统需求SR”分配到子系统/模块的功能或非功能需求。
