# 金融风控模块系统

一个高性能的实时金融风控模块，专为高频交易场景设计，能够处理百万级/秒的订单和成交数据，并在微秒级时间内完成风控规则评估和处置指令生成。

## 🚀 核心特性

- **高并发**: 支持百万级/秒事件处理
- **低延迟**: 微秒级响应时间
- **可扩展**: 支持动态规则配置和热更新
- **多维统计**: 支持账户、合约、产品、交易所、账户组等维度
- **实时监控**: 内置性能指标和监控

## 🏗️ 系统架构

```
risk_engine/
├── engine.py              # 同步风控引擎
├── async_engine.py        # 异步高性能引擎
├── rules.py               # 风控规则引擎
├── models.py              # 数据模型
├── actions.py             # 风控动作
├── metrics.py             # 指标系统
├── state.py               # 状态管理
├── config.py              # 配置管理
├── dimensions.py          # 维度管理
└── accel/                 # 加速模块
```

## 📋 风控规则

### 1. 单账户成交量限制
- 监控账户在指定时间窗口内的成交量
- 支持多维度统计（账户、合约、产品、交易所、账户组）
- 超过阈值时触发风控动作

### 2. 报单频率控制
- 监控账户在滑动时间窗口内的报单频率
- 支持动态阈值和时间窗口调整
- 超过阈值时暂停报单，回落后自动恢复

### 3. 扩展规则支持
- 基于 `Rule` 基类的可扩展规则框架
- 支持自定义风控逻辑
- 插件化架构设计

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 基本使用

```python
from risk_engine import RiskEngine, EngineConfig
from risk_engine.models import Order, Trade, Direction

# 创建引擎配置
config = EngineConfig(
    contract_to_product={"T2303": "T10Y"},
    deduplicate_actions=True,
)

# 创建风控引擎
engine = RiskEngine(config)

# 处理订单
order = Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 1, timestamp)
engine.on_order(order)

# 处理成交
trade = Trade(1, 1, "ACC_001", "T2303", 100.0, 1, timestamp)
engine.on_trade(trade)
```

### 异步高性能使用

```python
import asyncio
from risk_engine.async_engine import create_async_engine
from risk_engine.config import RiskEngineConfig

async def main():
    # 创建异步引擎配置
    config = RiskEngineConfig(
        contract_to_product={"T2303": "T10Y"},
        num_shards=128,
        worker_threads=8,
    )
    
    # 创建异步引擎
    engine = create_async_engine(config)
    
    # 启动引擎
    await engine.start()
    
    try:
        # 提交订单
        order = Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 1, timestamp)
        await engine.submit_order(order)
        
        # 提交成交
        trade = Trade(1, 1, "ACC_001", "T2303", 100.0, 1, timestamp)
        await engine.submit_trade(trade)
        
    finally:
        await engine.stop()

# 运行
asyncio.run(main())
```

## 📊 性能测试

运行性能基准测试：

```bash
# 异步高性能测试
python bench_async.py

# 基本性能测试
python bench.py
```

### 性能目标
- **吞吐量**: 1,000,000 事件/秒
- **延迟**: P99 < 1,000 微秒
- **并发**: 支持高并发事件处理

## 📖 使用示例

查看完整的使用示例：

```bash
python examples/basic_usage.py
```

示例包括：
- 基本风控引擎使用
- 异步高性能引擎使用
- 自定义规则开发
- 动态配置更新

## ⚙️ 配置说明

### 引擎配置

```python
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, StatsDimension

config = RiskEngineConfig(
    # 合约到产品映射
    contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
    
    # 成交量限制规则
    volume_limit=VolumeLimitRuleConfig(
        threshold=1000,  # 1000手
        dimension=StatsDimension.PRODUCT,
        metric=MetricType.TRADE_VOLUME
    ),
    
    # 报单频率限制规则
    order_rate_limit=OrderRateLimitRuleConfig(
        threshold=50,  # 50次/秒
        window_seconds=1,
        dimension=StatsDimension.ACCOUNT
    ),
    
    # 性能调优参数
    num_shards=128,        # 分片锁数量
    max_queue_size=1000000, # 最大队列大小
    batch_size=1000,       # 批处理大小
    worker_threads=8,      # 工作线程数
)
```

### 异步引擎配置

```python
from risk_engine.async_engine import AsyncEngineConfig

async_config = AsyncEngineConfig(
    max_concurrent_tasks=10000,  # 最大并发任务数
    task_timeout_ms=50,          # 任务超时时间
    batch_size=1000,             # 批处理大小
    num_workers=8,               # 工作线程数
    enable_batching=True,        # 启用批处理
    enable_async_io=True,        # 启用异步IO
)
```

## 🔧 自定义规则

### 创建自定义规则

```python
from risk_engine.rules import Rule, RuleContext, RuleResult
from risk_engine.actions import Action

class CustomRiskRule(Rule):
    def __init__(self, rule_id: str, threshold: float):
        self.rule_id = rule_id
        self.threshold = threshold
    
    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        # 自定义风控逻辑
        if order.volume > self.threshold:
            return RuleResult(
                actions=[Action.BLOCK_ORDER],
                reasons=[f"订单数量 {order.volume} 超过阈值 {self.threshold}"]
            )
        return None

# 添加自定义规则
engine.add_rule(CustomRiskRule("CUSTOM-RULE", 1000))
```

## 📈 监控和统计

### 获取性能统计

```python
# 同步引擎
stats = engine.snapshot()

# 异步引擎
stats = engine.get_stats()
print(f"订单处理: {stats['orders_processed']:,}")
print(f"成交处理: {stats['trades_processed']:,}")
print(f"动作生成: {stats['actions_generated']:,}")
print(f"平均延迟: {stats['avg_latency_ns']/1000:.2f} 微秒")
```

## 🚀 部署建议

### 硬件配置
- **CPU**: 建议16核以上，支持高频率
- **内存**: 建议32GB以上，根据并发量调整
- **网络**: 低延迟网络，支持高带宽
- **存储**: SSD存储，减少I/O延迟

### 系统调优

```bash
# 调整系统参数
echo 'net.core.rmem_max = 134217728' >> /etc/sysctl.conf
echo 'net.core.wmem_max = 134217728' >> /etc/sysctl.conf
echo 'vm.swappiness = 1' >> /etc/sysctl.conf

# 应用配置
sysctl -p
```

## 📚 文档

- [系统文档](SYSTEM_DOCUMENTATION.md) - 详细的系统说明和使用指南
- [API文档](risk_engine/) - 代码级别的API文档
- [示例代码](examples/) - 完整的使用示例

## 🤝 贡献

欢迎提交Issue和Pull Request来改进这个项目。

## 📄 许可证

本项目采用MIT许可证。

## 🔗 相关链接

- [Python官方文档](https://docs.python.org/)
- [asyncio文档](https://docs.python.org/3/library/asyncio.html)
- [金融风控最佳实践](https://www.bis.org/publ/bcbs128.pdf)
