# 金融风控模块系统 - 技术文档

## 目录
1. [系统概述](#系统概述)
2. [需求满足情况](#需求满足情况)
3. [系统架构](#系统架构)
4. [接口设计](#接口设计)
5. [核心功能实现](#核心功能实现)
6. [快速开始](#快速开始)
7. [详细使用指南](#详细使用指南)
8. [性能验证](#性能验证)
9. [系统优势](#系统优势)
10. [系统局限](#系统局限)

## 系统概述

本系统是一个高性能的实时金融风控模块，专为高频交易场景设计。系统采用分片锁架构、异步处理和批处理优化，能够处理百万级/秒的订单和成交数据，并在微秒级时间内完成风控规则评估和处置指令生成。

### 核心特性
- **高并发**: 支持百万级/秒事件处理
- **低延迟**: 微秒级响应时间（P99 < 1000微秒）
- **可扩展**: 插件化规则架构，支持动态配置和热更新
- **多维统计**: 支持账户、合约、产品、交易所、账户组等多维度统计
- **灵活配置**: 支持多种指标类型和动作类型的扩展

## 需求满足情况

### 1. 单账户成交量限制 
- **实现**: `VolumeLimitRule` 类
- **功能**: 监控账户/产品在当日的成交量，超过阈值时暂停交易
- **扩展点满足**:
  -  支持多种指标: 成交量、成交金额、报单量、撤单量
  -  支持多维度统计: 账户、合约、产品、交易所、账户组
  -  可配置阈值和统计维度

### 2. 报单频率控制 
- **实现**: `OrderRateLimitRule` 类
- **功能**: 监控账户在滑动时间窗口内的报单频率
- **扩展点满足**:
  -  支持动态调整阈值
  -  支持动态调整时间窗口（秒级或纳秒级）
  -  自动恢复功能

### 3. Action处置指令 
- **实现**: `Action` 枚举类和 `EmittedAction` 数据类
- **支持的动作类型**:
  - 账户维度: 暂停/恢复账户交易
  - 报单维度: 暂停/恢复报单
  - 合约维度: 暂停/恢复特定合约
  - 产品维度: 暂停/恢复产品交易
  - 其他: 告警、强制减仓、追加保证金等
- **扩展点满足**:
  -  一个规则可关联多个Action
  -  Action类型可扩展

### 4. 多维统计引擎 
- **实现**: `DimensionKey` 和 `InstrumentCatalog`
- **功能**: 支持多维度的实时统计和聚合
- **扩展点满足**:
  -  支持合约维度和产品维度统计
  -  易于新增统计维度
  -  O(1)时间复杂度的维度查询


## 系统架构详解

### 1.整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     客户端应用层                          │
│  (交易终端、API接入、监控系统、报表系统)                   │
└────────────────────┬───────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────┐
│                   风控引擎层                             │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  同步引擎   │  │  异步引擎    │  │  规则引擎    │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
└────────────────────┬───────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────┐
│                   核心组件层                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │状态管理器│  │统计引擎  │  │动作处理器│  │配置管理││
│  └──────────┘  └──────────┘  └──────────┘  └────────┘│
└────────────────────┬───────────────────────────────────┘
                     │
┌────────────────────▼───────────────────────────────────┐
│                   基础设施层                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│
│  │分片锁机制│  │内存池    │  │性能监控  │  │日志系统││
│  └──────────┘  └──────────┘  └──────────┘  └────────┘│
└─────────────────────────────────────────────────────────┘
```

### 2.数据流程

```
订单/成交 → 引擎接收 → 规则评估 → 统计更新 → 动作生成 → 结果返回
    ↓           ↓           ↓           ↓           ↓
  验证      并发控制      风险计算      状态同步      动作执行
```

### 3. 关键设计

#### 3.1 分片锁架构

系统采用128个分片锁，通过账户ID哈希分配，大幅降低锁竞争：

```python
shard_id = hash(account_id) % 128
with self.locks[shard_id]:
    # 处理逻辑
```

#### 3.2 异步处理模型

```
Producer → Queue → Worker Pool → Result Aggregator
   ↓         ↓          ↓              ↓
批量提交   缓冲队列     并行处理          结果聚合
```

#### 3.3 内存优化策略

- 使用 `__slots__` 减少对象内存占用
- 对象池复用，减少GC压力
- 批处理减少内存分配

```
risk_engine/
├── models.py              # 数据模型定义（Order、Trade、Direction）
├── engine.py              # 同步风控引擎核心
├── async_engine.py        # 异步高性能引擎（百万级TPS）
├── rules.py               # 风控规则框架和具体规则实现
├── actions.py             # 风控动作定义（可扩展）
├── metrics.py             # 统计指标类型（可扩展）
├── dimensions.py          # 多维度统计支持
├── state.py               # 状态管理（线程安全）
├── config.py              # 配置管理（支持动态更新）
└── accel/                 # 性能加速模块
    ├── __init__.py
    ├── cython_ext.py      # Cython加速（可选）
    └── numba_jit.py       # Numba JIT加速（可选）
```

### 核心设计原则
1. **分片锁架构**: 使用64-128个分片减少锁竞争
2. **异步处理**: 支持高并发事件处理
3. **批处理优化**: 批量处理提高吞吐量
4. **内存优化**: 使用`slots=True`减少内存占用
5. **插件化设计**: 规则、指标、动作均可独立扩展

## 接口设计

### 1. 数据模型接口

```python
# 订单数据模型
@dataclass(slots=True)
class Order:
    oid: int                           # 订单唯一标识符
    account_id: str                    # 交易账户编号
    contract_id: str                   # 合约代码
    direction: Direction               # 买卖方向（Bid/Ask）
    price: float                       # 订单价格
    volume: int                        # 订单数量
    timestamp: int                     # 时间戳（纳秒）
    exchange_id: Optional[str] = None  # 交易所（扩展维度）
    account_group_id: Optional[str] = None  # 账户组（扩展维度）

# 成交数据模型
@dataclass(slots=True)
class Trade:
    tid: int                           # 成交唯一标识符
    oid: int                           # 关联的订单ID
    price: float                       # 成交价格
    volume: int                        # 实际成交量
    timestamp: int                     # 成交时间戳（纳秒）
    account_id: Optional[str] = None  # 账户ID（可从订单获取）
    contract_id: Optional[str] = None # 合约ID（可从订单获取）
```

### 2. 风控规则接口

```python
# 规则基类
class Rule(ABC):
    @abstractmethod
    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        """处理订单事件"""
        pass
    
    @abstractmethod
    def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
        """处理成交事件"""
        pass

# 规则结果
@dataclass
class RuleResult:
    actions: List[Action]              # 触发的动作列表
    reasons: List[str]                 # 触发原因
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3. 配置接口

```python
# 成交量限制规则配置
@dataclass
class VolumeLimitRuleConfig:
    threshold: float                   # 阈值
    dimension: StatsDimension          # 统计维度
    metric: MetricType                 # 指标类型
    reset_daily: bool = True          # 是否每日重置

# 报单频率限制规则配置
@dataclass
class OrderRateLimitRuleConfig:
    threshold: int                     # 频率阈值
    window_seconds: Optional[int]      # 时间窗口（秒）
    window_ns: Optional[int]           # 时间窗口（纳秒）
    dimension: StatsDimension          # 统计维度

# 风控引擎配置
@dataclass
class RiskEngineConfig:
    contract_to_product: Dict[str, str]     # 合约到产品映射
    volume_limit: Optional[VolumeLimitRuleConfig]
    order_rate_limit: Optional[OrderRateLimitRuleConfig]
    num_shards: int = 64                    # 分片数量
    worker_threads: int = 4                 # 工作线程数
```

## 核心功能实现

### 1. 成交量限制规则
```python
class VolumeLimitRule(Rule):
    """
    功能：监控指定维度的成交量/金额等指标
    触发：超过阈值时暂停相应维度的交易
    扩展：支持多种指标类型和统计维度
    """
```

### 2. 报单频率控制规则
```python
class OrderRateLimitRule(Rule):
    """
    功能：监控滑动时间窗口内的报单频率
    触发：超过阈值时暂停报单，自动恢复
    扩展：支持动态调整阈值和时间窗口
    """
```

### 3. 多维统计引擎
```python
class StateManager:
    """
    功能：管理多维度的实时统计数据
    特性：线程安全、高性能、可扩展
    支持：账户、合约、产品、交易所、账户组等维度
    """
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 基本使用示例

```python
from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.config import StatsDimension

# 1. 创建配置
config = RiskEngineConfig(
    # 合约到产品映射（重要！）
    contract_to_product={
        "T2303": "T10Y",  # 10年期国债期货2303合约
        "T2306": "T10Y",  # 10年期国债期货2306合约
        "TF2303": "T5Y",  # 5年期国债期货2303合约
    },
    
    # 成交量限制规则
    volume_limit=VolumeLimitRuleConfig(
        threshold=1000,                    # 1000手
        dimension=StatsDimension.PRODUCT,  # 按产品维度统计
        metric=MetricType.TRADE_VOLUME     # 统计成交量
    ),
    
    # 报单频率限制规则
    order_rate_limit=OrderRateLimitRuleConfig(
        threshold=50,                      # 50次/秒
        window_seconds=1,                  # 1秒时间窗口
        dimension=StatsDimension.ACCOUNT   # 按账户维度统计
    )
)

# 2. 创建风控引擎
engine = RiskEngine(config)

# 3. 处理订单
order = Order(
    oid=1,
    account_id="ACC_001",
    contract_id="T2303",
    direction=Direction.BID,
    price=100.5,
    volume=10,
    timestamp=1_700_000_000_000_000_000  # 纳秒时间戳
)
actions = engine.on_order(order)
if actions:
    for action in actions:
        print(f"触发动作: {action.type.name}, 原因: {action.reason}")

# 4. 处理成交
trade = Trade(
    tid=1,
    oid=1,
    price=100.5,
    volume=10,
    timestamp=1_700_000_000_000_000_000,
    account_id="ACC_001",  # 可选，会从订单获取
    contract_id="T2303"    # 可选，会从订单获取
)
actions = engine.on_trade(trade)
```

## 详细使用指南

### 1. 多维度统计示例

```python
# 配置多维度统计
config = RiskEngineConfig(
    contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
    contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
    
    # 按产品维度统计成交金额
    volume_limit=VolumeLimitRuleConfig(
        threshold=100_000_000,              # 1亿元
        dimension=StatsDimension.PRODUCT,
        metric=MetricType.TRADE_NOTIONAL    # 成交金额
    )
)
```

### 2. 自定义规则开发

```python
from risk_engine.rules import Rule, RuleContext, RuleResult
from risk_engine.actions import Action

class CustomPriceDeviationRule(Rule):
    """自定义规则：价格偏离检查"""
    
    def __init__(self, rule_id: str, max_deviation: float):
        self.rule_id = rule_id
        self.max_deviation = max_deviation
        self.reference_prices = {}
    
    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        ref_price = self.reference_prices.get(order.contract_id, order.price)
        deviation = abs(order.price - ref_price) / ref_price
        
        if deviation > self.max_deviation:
            return RuleResult(
                actions=[Action.BLOCK_ORDER, Action.ALERT],
                reasons=[f"价格偏离{deviation:.2%}超过阈值{self.max_deviation:.2%}"]
            )
        
        self.reference_prices[order.contract_id] = order.price
        return None

# 添加自定义规则
engine.add_rule(CustomPriceDeviationRule("PRICE_CHECK", 0.05))
```

### 3. 异步高性能引擎使用

```python
import asyncio
from risk_engine.async_engine import create_async_engine

async def high_performance_example():
    # 创建异步引擎
    engine = create_async_engine(config)
    await engine.start()
    
    # 批量提交订单
    orders = []
    for i in range(10000):
        order = Order(i, f"ACC_{i%100}", "T2303", Direction.BID, 100.0, 1, i)
        orders.append(engine.submit_order(order))
    
    # 并发处理
    await asyncio.gather(*orders)
    
    # 获取统计信息
    stats = engine.get_stats()
    print(f"处理订单: {stats['orders_processed']:,}")
    print(f"平均延迟: {stats['avg_latency_ns']/1000:.2f} 微秒")
    
    await engine.stop()
```

### 4. 动态配置更新

```python
# 运行时更新规则配置
engine.update_rule_config("VOLUME_LIMIT", {
    "threshold": 2000,  # 提高阈值到2000手
    "metric": MetricType.TRADE_NOTIONAL  # 改为监控成交金额
})

# 添加新规则
from risk_engine.config import DynamicRuleConfig
new_rule = DynamicRuleConfig(
    rule_id="CANCEL_RATE_LIMIT",
    rule_type="order_rate_limit",
    config={
        "threshold": 10,
        "window_seconds": 60,
        "metric": MetricType.CANCEL_COUNT
    },
    actions=["SUSPEND_ORDERING", "ALERT"]
)
engine.add_dynamic_rule(new_rule)
```

## 性能验证

### 1. 运行性能基准测试

```bash
# 测试异步引擎性能（推荐）
python bench_async.py

# 测试基础引擎性能
python bench.py
```

### 2. 预期性能指标

- **吞吐量**: > 1,000,000 事件/秒
- **延迟**: P99 < 1,000 微秒
- **内存使用**: < 1GB for 1M events
- **CPU使用**: 可充分利用多核

### 3. 性能验证方法

```python
# 验证百万级吞吐量
python examples/benchmark.py --events 1000000 --threads 8

# 验证微秒级延迟
python examples/benchmark.py --measure-latency --percentiles 50,90,99,99.9

# 验证多维度统计性能
python examples/benchmark.py --dimensions account,contract,product
```

## 系统优势

### 1. 高性能架构
- **分片锁设计**: 64-128个分片，大幅减少锁竞争
- **异步处理**: 支持百万级并发，充分利用多核CPU
- **批处理优化**: 批量处理事件，提高吞吐量
- **内存优化**: 使用`slots=True`和对象池，减少GC压力

### 2. 可扩展性
- **插件化规则**: 基于抽象基类，易于扩展新规则
- **灵活的指标**: 支持自定义指标类型
- **多维度统计**: 易于添加新的统计维度
- **动态配置**: 支持运行时更新规则和配置

### 3. 易用性
- **简洁的API**: 直观的接口设计
- **丰富的示例**: 完整的使用示例和测试用例
- **详细的文档**: 全面的技术文档和注释

## 系统局限

### 1. 单机限制
- 当前设计为单机部署，极限性能受单机硬件限制
- 如需更高性能，需要考虑分布式架构

### 2. 内存依赖
- 高并发场景下内存使用量较大
- 建议配置充足的内存（16GB+）

### 3. 规则复杂度
- 复杂规则可能影响延迟
- 建议将复杂计算异步化或预计算

### 4. 持久化
- 当前版本未包含持久化功能
- 重启后需要重新加载状态

## 如何验证系统

### 1. 功能验证
```bash
# 运行所有单元测试
python -m pytest tests/ -v

# 运行集成测试
python tests/test_integration.py
```

### 2. 性能验证
```bash
# 运行性能基准测试
python bench_async.py --duration 60 --report

# 验证延迟分布
python bench_async.py --measure-latency --output latency_report.json
```

### 3. 完整示例验证
```bash
# 运行完整的示例程序
python examples/complete_demo.py

# 模拟真实交易场景
python examples/trading_simulation.py
```

### 4. 压力测试
```bash
# 极限压力测试
python examples/stress_test.py --rate 2000000 --duration 300
```

## 联系和支持

如有任何问题或建议，请通过以下方式联系：
- 提交Issue到项目仓库
- 查看examples/目录下的更多示例
- 参考tests/目录下的测试用例


