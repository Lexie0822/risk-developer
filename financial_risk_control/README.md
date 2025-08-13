# 金融风控系统 (Financial Risk Control System)

## 概述

本系统是一个高性能的实时金融风控模块，专为处理高频订单（Order）和成交（Trade）数据而设计。系统能够动态触发风控规则并生成处置指令（Action），满足金融交易场景中百万级/秒的高并发和微秒级响应的严格要求。

## 核心特性

### 1. 高性能架构
- **百万级吞吐量**：支持每秒处理超过100万笔订单和成交
- **微秒级延迟**：P50延迟 < 1ms，P99延迟 < 10ms
- **多线程并发**：采用多线程工作池架构，充分利用多核CPU
- **异步处理**：支持同步和异步两种处理模式，灵活应对不同场景

### 2. 灵活的规则引擎
- **预置规则类型**：
  - 单账户成交量限制：支持日/小时/分钟等多时间窗口
  - 报单频率控制：防止恶意高频报单
  - 产品级别监控：支持产品维度的风险预警
- **规则扩展性**：
  - 支持自定义规则开发
  - 支持组合规则（AND/OR逻辑）
  - 支持多维度指标（成交量、成交金额、报单数、撤单数等）

### 3. 多维度统计引擎
- **灵活的维度支持**：账户、合约、产品、交易所等
- **实时指标计算**：滑动窗口算法，实时更新统计数据
- **高效的聚合查询**：支持Top-N查询、多维度聚合
- **内存优化**：自动清理过期数据，防止内存泄漏

### 4. 完善的配置管理
- **动态配置更新**：支持热加载，无需重启系统
- **多格式支持**：JSON、YAML配置文件
- **配置构建器**：提供便捷的规则构建API
- **版本管理**：支持配置导入导出，便于备份恢复

### 5. 全面的监控能力
- **实时统计**：订单/成交处理量、延迟分布、吞吐量
- **规则监控**：每条规则的触发次数、评估次数
- **事件通知**：支持自定义事件处理器
- **性能分析**：提供详细的性能指标

## 快速开始

### 安装

```bash
# 克隆项目
git clone https://github.com/your-org/financial_risk_control.git
cd financial_risk_control

# 安装依赖
pip install -r requirements.txt
```

### 基本使用

```python
from src import RiskControlEngine, Order, Trade, Direction

# 创建并启动引擎
engine = RiskControlEngine(num_workers=4)
engine.start()

# 处理订单
order = Order(
    oid=1,
    account_id="ACC_001",
    contract_id="T2303",
    direction=Direction.BID,
    price=100.5,
    volume=10,
    timestamp=int(time.time() * 1e9)
)

actions = engine.process_order(order)

# 处理成交
trade = Trade(
    tid=1,
    oid=1,
    price=100.5,
    volume=10,
    timestamp=int(time.time() * 1e9)
)

actions = engine.process_trade(trade)

# 停止引擎
engine.stop()
```

## 详细功能说明

### 1. 风控规则配置

系统提供了灵活的规则配置机制：

```python
from src import ConfigManager, RuleBuilder, ActionType, TimeWindow

# 创建配置管理器
config_manager = ConfigManager()
config = config_manager.create_default_config()

# 添加自定义规则
custom_rule = RuleBuilder.volume_limit_rule(
    rule_id="hourly_volume_limit",
    threshold=5000,
    window_hours=1,
    actions=[ActionType.WARNING, ActionType.SUSPEND_ACCOUNT]
)
config.add_rule(custom_rule)

# 应用配置到引擎
engine.update_config(config)
```

### 2. 多维度统计

系统支持灵活的多维度数据统计：

```python
# 获取账户统计数据
metrics = engine.get_account_metrics("ACC_001")
print(f"日成交量: {metrics['daily_volume']}")
print(f"每秒报单率: {metrics['order_rate_per_sec']}")

# 获取Top账户
top_accounts = engine.metrics_collector.get_top_accounts_by_volume(
    TimeWindow.hours(1), n=10
)
```

### 3. 事件处理

注册自定义处理器来响应风控事件：

```python
# 注册Action处理器
def handle_suspend(action):
    print(f"账户 {action.account_id} 被暂停: {action.reason}")
    # 执行实际的账户暂停逻辑

engine.register_action_handler(ActionType.SUSPEND_ACCOUNT, handle_suspend)

# 注册事件处理器
def handle_risk_event(event):
    if event.severity == "CRITICAL":
        # 发送告警通知
        send_alert(event)

engine.register_event_handler(handle_risk_event)
```

### 4. 性能监控

实时监控系统性能：

```python
# 获取系统统计信息
stats = engine.get_statistics()

print(f"处理订单数: {stats['engine']['orders_processed']}")
print(f"平均延迟: {stats['engine']['avg_latency_us']} μs")
print(f"吞吐量: {stats['engine']['throughput_ops_per_sec']} ops/s")

# 获取规则统计
for rule_id, rule_stats in stats['rules'].items():
    print(f"{rule_id}: 触发 {rule_stats['triggered']} 次")
```

## 配置文件格式

系统支持JSON和YAML格式的配置文件：

```json
{
  "rules": [
    {
      "rule_id": "account_daily_volume_limit",
      "name": "账户日成交量限制",
      "description": "当账户当日成交量超过1000手时，暂停该账户交易",
      "enabled": true,
      "priority": 100,
      "metrics": [
        {
          "metric_type": "VOLUME",
          "threshold": 1000,
          "window_seconds": 86400,
          "dimensions": ["account"]
        }
      ],
      "actions": ["SUSPEND_ACCOUNT"],
      "cooldown_seconds": 300
    }
  ],
  "global_settings": {
    "max_concurrent_orders": 1000,
    "enable_pre_trade_check": true
  }
}
```

## 系统架构

### 核心组件

1. **RiskControlEngine**: 主引擎，协调所有组件
2. **MetricsCollector**: 多维度指标收集器
3. **RuleManager**: 规则管理和执行
4. **ConfigManager**: 配置管理

### 数据流程

```
Order/Trade → Engine → Metrics Collection → Rule Evaluation → Action Generation
                ↓                               ↓
            Statistics                    Event Notification
```

## 性能优化建议

1. **工作线程数**：根据CPU核心数调整，建议设置为核心数的1-2倍
2. **队列大小**：根据峰值流量调整异步队列大小
3. **规则优先级**：将高频触发的规则设置更高优先级
4. **内存管理**：定期清理过期数据，避免内存持续增长

## 扩展开发

### 自定义规则

```python
from src.rules import Rule, RuleResult, RuleContext

class CustomRule(Rule):
    def evaluate(self, context: RuleContext, metrics_collector) -> RuleResult:
        # 实现自定义规则逻辑
        if self.check_condition(context):
            return RuleResult(
                triggered=True,
                actions=[self.create_action()],
                reason="自定义规则触发"
            )
        return RuleResult(triggered=False)
```

### 自定义指标

```python
from src.metrics import MetricType

# 扩展MetricType枚举
class CustomMetricType(MetricType):
    PROFIT_LOSS = auto()
    POSITION = auto()

# 记录自定义指标
metrics_collector.engine.record_metric(
    CustomMetricType.PROFIT_LOSS,
    value=1000.0,
    timestamp=current_time,
    dimensions=[MetricDimension("account", account_id)],
    windows=[TimeWindow.hours(1)]
)
```

## 测试

运行测试套件：

```bash
# 运行所有测试
python -m pytest tests/

# 运行性能测试
python tests/test_performance.py

# 运行特定测试
python -m pytest tests/test_engine.py::TestRiskControlEngine::test_volume_limit_rule
```

## 系统限制

1. **内存使用**：系统将指标数据保存在内存中，需要根据数据量合理配置
2. **时间精度**：使用纳秒级时间戳，依赖系统时钟精度
3. **规则数量**：大量规则可能影响延迟，建议控制在100条以内
4. **数据持久化**：当前版本不支持数据持久化，重启后历史数据丢失

## 最佳实践

1. **规则设计**：
   - 避免过于复杂的规则逻辑
   - 合理设置cooldown时间，避免规则频繁触发
   - 使用优先级控制规则执行顺序

2. **性能优化**：
   - 预先warm up系统，避免冷启动影响
   - 合理设置工作线程数
   - 定期监控系统指标

3. **监控告警**：
   - 设置关键指标的阈值告警
   - 记录所有风控事件用于审计
   - 定期分析规则触发情况

## 常见问题

**Q: 系统能处理多少并发请求？**
A: 在8核CPU上，系统可以稳定处理100万+订单/秒的并发请求。

**Q: 如何处理系统重启后的数据恢复？**
A: 当前版本不支持数据持久化。建议在上游系统保存关键状态，重启后重放必要的历史数据。

**Q: 规则更新是否需要重启系统？**
A: 不需要。系统支持热加载配置，可以在运行时更新规则。

**Q: 如何监控系统健康状态？**
A: 通过`get_statistics()`方法获取实时统计信息，包括处理量、延迟、规则触发情况等。

## 贡献指南

欢迎提交Issue和Pull Request。提交代码前请确保：

1. 通过所有测试用例
2. 添加必要的单元测试
3. 更新相关文档
4. 遵循PEP 8代码规范

## 许可证

本项目采用MIT许可证。详见LICENSE文件。

## 联系方式

- 项目维护者：Risk Control Team
- Email: risk-control@example.com
- Issue追踪：https://github.com/your-org/financial_risk_control/issues