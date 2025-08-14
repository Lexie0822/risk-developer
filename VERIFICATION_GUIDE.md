# 金融风控模块验证指南

## 如何验证系统满足项目要求

### 1. 运行完整验证脚本

最简单的方式是运行我们提供的验证脚本，它会自动测试所有需求：

```bash
python3 verify_requirements.py
```

这个脚本会：
- 逐项验证4个核心需求
- 进行性能测试
- 输出详细的验证报告

### 2. 运行单元测试

项目包含完整的测试套件：

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行特定测试
python3 -m pytest tests/test_rules.py -v      # 测试风控规则
python3 -m pytest tests/test_engine.py -v     # 测试引擎核心
python3 -m pytest tests/test_performance.py -v # 测试性能
```

### 3. 运行示例程序

查看系统实际运行效果：

```bash
# 完整功能演示
python3 examples/complete_demo.py

# 性能基准测试
python3 bench_async.py
```

### 4. 手动验证各项需求

#### 需求1：单账户成交量限制
- 文件位置：`risk_engine/rules.py`中的`AccountTradeMetricLimitRule`类
- 验证点：
  - 支持成交量、成交金额、报单量、撤单量等多种指标
  - 支持账户、合约、产品、交易所、账户组等多维度统计
  - 可配置阈值

#### 需求2：报单频率控制
- 文件位置：`risk_engine/rules.py`中的`OrderRateLimitRule`类
- 验证点：
  - 滑动时间窗口统计
  - 支持动态调整阈值和时间窗口
  - 自动恢复功能

#### 需求3：Action处置指令
- 文件位置：`risk_engine/actions.py`
- 验证点：
  - 支持多种Action类型（暂停交易、告警、强制减仓等）
  - 一个规则可触发多个Action

#### 需求4：多维统计引擎
- 文件位置：`risk_engine/dimensions.py`和`risk_engine/state.py`
- 验证点：
  - 支持合约和产品维度统计
  - 易于扩展新维度
  - O(1)查询复杂度

### 5. 性能验证

运行性能测试脚本：

```bash
# 异步引擎性能测试
python3 bench_async.py

# 查看输出应该显示：
# - 吞吐量 > 1,000,000 事件/秒
# - 延迟 P99 < 1000 微秒
```

### 6. 查看项目结构

确认所有必需的组件都已实现：

```bash
tree risk_engine/
```

应该包含：
- models.py - 数据模型
- engine.py - 同步引擎
- async_engine.py - 异步引擎
- rules.py - 风控规则
- actions.py - 动作定义
- metrics.py - 指标类型
- dimensions.py - 维度支持
- state.py - 状态管理
- config.py - 配置管理

### 7. 检查文档完整性

README.md应该包含：
- 系统概述
- 架构说明
- 接口设计
- 使用指南
- 性能测试方法
- 系统优势和局限

## 验证清单

- [ ] verify_requirements.py 运行成功，所有测试通过
- [ ] 示例程序能正常运行
- [ ] 性能测试达到要求（百万级TPS，微秒级延迟）
- [ ] 文档完整清晰
- [ ] 代码结构合理，易于扩展

## 常见问题

1. **如果没有pytest怎么办？**
   - 可以直接运行 `python3 verify_requirements.py`
   - 或者运行示例程序查看功能

2. **性能测试结果不理想？**
   - 确保使用异步引擎 `bench_async.py`
   - 检查是否有足够的CPU核心
   - 考虑调整配置参数（num_shards, worker_threads）

3. **需要更详细的测试？**
   - 查看 tests/ 目录下的具体测试用例
   - 修改示例程序进行自定义测试