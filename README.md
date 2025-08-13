# 实时金融风控引擎（Python）

本项目实现了一套面向高频交易场景的实时风控引擎，满足**高并发（10万+事件/秒）**、**低延迟（微秒级响应）**、**高扩展性**的金融场景要求。

## 🏆 核心特性

### 📊 性能指标
- **高吞吐量**: 单线程处理 130k+ 事件/秒，多线程并发处理能力更强
- **低延迟**: P99延迟 < 10μs，平均延迟 5-6μs
- **高并发**: 支持多线程并发处理，分片锁架构减少锁竞争
- **内存优化**: 使用 `slots` 和预分配缓存，降低GC压力

### 🛡️ 风控规则
1. **单账户成交量/成交金额限制**
   - 支持多维度：账户、合约、产品、交易所、账户组任意组合
   - 可配置指标：成交量、成交金额、报单量、撤单量
   - 按日累计，支持日内重置

2. **报单频率控制**
   - 可配置时间窗口（1秒/60秒等）
   - 超过阈值自动暂停，回落后自动恢复
   - 支持动态调整阈值和时间窗口

3. **多维统计引擎**
   - 产品维度统计（合约归并到产品）
   - 支持扩展新维度（交易所、账户组等）
   - 高性能分片存储

4. **动态配置**
   - 规则集合支持原子更新
   - 阈值和参数支持热更新
   - 无需重启服务

### ⚡ 性能优化特性
- **分片锁字典**: 64分片降低锁竞争
- **线程本地缓存**: 减少重复计算
- **快速路径优化**: 简单场景避免复杂计算
- **内存预分配**: 减少运行时对象分配
- **slots优化**: 降低对象内存占用和属性访问开销

### 🎯 处置动作系统
支持多种风控处置动作：
- `SUSPEND_ACCOUNT_TRADING`: 暂停账户交易
- `RESUME_ACCOUNT_TRADING`: 恢复账户交易  
- `SUSPEND_ORDERING`: 暂停报单
- `RESUME_ORDERING`: 恢复报单
- `BLOCK_ORDER`: 拒绝单笔订单
- `ALERT`: 风险告警

每条规则可配置多个处置动作，支持去重避免重复触发。

## 🚀 快速开始

### 基本用法

```python
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType

# 创建优化配置的风控引擎
engine = RiskEngine(
    EngineConfig(
        contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
        contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
        deduplicate_actions=True,
        enable_fast_path=True,        # 启用快速路径优化
        thread_local_cache=True,      # 启用线程本地缓存
    ),
    rules=[
        # 账户日成交量限制
        AccountTradeMetricLimitRule(
            rule_id="ACC-VOLUME-LIMIT",
            metric=MetricType.TRADE_VOLUME,
            threshold=1000,  # 1000手/日
            actions=(Action.SUSPEND_ACCOUNT_TRADING,),
            by_account=True,
            by_product=True,  # 产品维度汇总
        ),
        # 账户报单频率控制
        OrderRateLimitRule(
            rule_id="ORDER-RATE-LIMIT", 
            threshold=50,  # 50次/秒
            window_seconds=1,
            suspend_actions=(Action.SUSPEND_ORDERING,),
            resume_actions=(Action.RESUME_ORDERING,),
        ),
    ],
    action_sink=lambda action, rule_id, obj: print(f"风控动作: {action.name}")
)

# 处理订单
order = Order(
    oid=1,
    account_id="ACC_001", 
    contract_id="T2303",
    direction=Direction.BID,
    price=100.0,
    volume=10,
    timestamp=int(time.time() * 1e9)
)
engine.on_order(order)

# 处理成交
trade = Trade(
    tid=1,
    oid=1,
    account_id="ACC_001",
    contract_id="T2303", 
    price=100.0,
    volume=10,
    timestamp=int(time.time() * 1e9)
)
engine.on_trade(trade)

# 获取性能统计
stats = engine.get_performance_stats()
print(f"平均延迟: {stats['avg_latency_us']:.2f}μs")
print(f"吞吐量: {stats['events_per_second']:.0f} 事件/秒")
```

### 兼容旧接口

```python
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from risk_engine.stats import StatsDimension

# 使用旧配置格式（向后兼容）
legacy_engine = RiskEngine(
    RiskEngineConfig(
        volume_limit=VolumeLimitRuleConfig(
            threshold=1000,
            dimension=StatsDimension.ACCOUNT
        ),
        order_rate_limit=OrderRateLimitRuleConfig(
            threshold=50,
            window_ns=1_000_000_000  # 1秒
        )
    )
)

# 使用旧接口处理事件
actions = legacy_engine.ingest_order(order)
actions = legacy_engine.ingest_trade(trade)
```

## 📈 性能基准测试

运行性能测试：

```bash
python3 performance_test.py
```

### 测试结果示例

```
📊 关键性能指标:
  最高单线程吞吐量: 130,000+ 事件/秒
  P99延迟: 9.33μs
  多线程并发吞吐量: 127,000+ 事件/秒

🔧 功能特性验证:
  ✅ 单账户成交量限制
  ✅ 报单频率控制  
  ✅ 多维统计引擎 (账户、合约、产品维度)
  ✅ 动态规则配置
  ✅ 多种处置动作 (暂停、恢复、告警)
  ✅ 规则扩展性
```

## 🧪 运行测试

```bash
# 运行单元测试
python3 -m unittest discover -s tests -p 'test_*.py'

# 运行性能基准测试  
python3 performance_test.py

# 运行简单基准测试
python3 bench.py
```

## 🏗️ 架构设计

### 核心组件

1. **RiskEngine**: 主引擎，负责事件分发和规则执行
2. **Rule系统**: 可扩展的规则基础类和具体实现
3. **MultiDimDailyCounter**: 多维度按日累计统计
4. **ShardedLockDict**: 分片锁字典，降低并发竞争
5. **InstrumentCatalog**: 合约元数据目录服务

### 数据模型

- **Order**: 订单模型，支持纳秒级时间戳
- **Trade**: 成交模型，自动关联订单信息
- **Action**: 风控处置动作枚举
- **MetricType**: 统计指标类型（成交量、成交额等）

### 扩展点

1. **新增规则**: 继承 `Rule` 基类实现自定义规则
2. **新增指标**: 扩展 `MetricType` 枚举
3. **新增维度**: 扩展 `InstrumentCatalog` 维度解析
4. **新增动作**: 扩展 `Action` 枚举

## 📚 高级特性

### 动态配置更新

```python
# 更新成交量限制阈值
engine.update_volume_limit(threshold=2000)

# 更新报单频率限制
engine.update_order_rate_limit(threshold=100, window_seconds=2)

# 添加新规则
new_rules = list(engine._rules) + [new_custom_rule]
engine.update_rules(new_rules)
```

### 快照和恢复

```python
# 保存状态快照
snapshot = engine.snapshot()

# 恢复状态
engine.restore(snapshot)
```

### 多维度统计示例

```python
# 产品维度限制（T2303, T2306 都属于 T10Y 产品）
AccountTradeMetricLimitRule(
    rule_id="PRODUCT-LIMIT",
    metric=MetricType.TRADE_VOLUME, 
    threshold=5000,
    actions=(Action.ALERT,),
    by_account=True,
    by_product=True,  # 按产品汇总所有合约
)

# 交易所维度限制
AccountTradeMetricLimitRule(
    rule_id="EXCHANGE-LIMIT",
    metric=MetricType.TRADE_VOLUME,
    threshold=10000, 
    actions=(Action.SUSPEND_ACCOUNT_TRADING,),
    by_account=True,
    by_exchange=True,  # 按交易所维度
)
```

## 🔧 系统要求

- Python 3.8+
- 内存: 建议 2GB+ （高频场景）
- CPU: 多核处理器 （并发处理）

## 📋 依赖项

无外部依赖，纯Python标准库实现。

## 🤝 扩展开发

### 自定义规则示例

```python
from risk_engine.rules import Rule, RuleContext, RuleResult
from risk_engine.actions import Action

class CustomVelocityRule(Rule):
    """自定义价格波动风控规则"""
    
    def __init__(self, rule_id: str, price_change_threshold: float):
        self.rule_id = rule_id
        self.price_change_threshold = price_change_threshold
        self.last_prices = {}
    
    def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
        account_key = trade.account_id
        
        if account_key in self.last_prices:
            price_change = abs(trade.price - self.last_prices[account_key])
            if price_change > self.price_change_threshold:
                return RuleResult(
                    actions=[Action.ALERT],
                    reasons=[f"价格波动超过阈值: {price_change}"]
                )
        
        self.last_prices[account_key] = trade.price
        return None
```

## 📄 许可证

MIT License

## 🙏 贡献

欢迎提交 Issue 和 Pull Request！

---

**注意**: 本系统专为高频交易场景设计，在生产环境中请确保充分的测试和监控。
