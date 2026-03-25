# SDD-TEE v4.0: 健壮性与现实主义演进方案 (Robust & Realism)

## 1. 核心目标
解决前三版本中存在的：指标偏低、空实现、缺乏纠错、缺乏迭代、测试不足五个系统性问题。

## 2. 技术改进项

### 2.1 统计精度修复 (Precision Metrics)
- **Sum-of-Turns**: 统计 Agentic 循环中每一轮的增量消耗，解决累计值覆盖导致的数据偏低。
- **Physical Audit**: 最终 LOC 以 `wc -l` 物理扫描为准，不再信任模型返回的统计。
- **Safe Aggregation**: 处理所有 `0`, `0.0`, `0m0s`, `None` 异常，确保报告数据连续。

### 2.2 闭环自愈机制 (Self-Correction Loop)
- **Inner-Loop Validation**: 在 ST-5 阶段结束后立即运行 `go build` 或 `ruff`。
- **Error Feedback**: 将编译/检查失败的 Stdout 重新作为 Input 发送给模型进行修复。

### 2.3 真实性模拟 (Real-world Simulation)
- **ST-1.5 Iteration**: 强制模型对复杂 AR 进行方案二选一或细节澄清。
- **Session Reset Persistence**: 确保每轮 AR 的起始环境是“干净但包含前序代码”的，模拟真实的增量开发。

### 2.4 测试驱动增强 (TDD Specs)
- **Test Specs**: 新增 `specs/testing/` 目录，包含原 `agentcube` 的核心测试逻辑。
- **AR-Test Mapping**: 每个 AR 必须包含对应的单元测试产出，否则 QT 质量分为 0。

## 3. 实施路径
1. 梳理测试用例规范 (`specs/test_spec.md`)。
2. 重构 `scripts/utils/recover_all_tokens.py` 为标准组件。
3. 升级 `orchestration/supervise_v4.sh` 引入纠错逻辑。
