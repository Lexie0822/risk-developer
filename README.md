# 金融风控模块系统 - 使用与技术说明

## 目录
- 系统概述
- 需求满足情况
- 系统架构与数据流
- 接口设计（模型、规则、配置）
- 核心功能说明
- 快速开始
- 详细使用指南（多维统计、自定义规则、异步引擎、动态配置）
- 性能验证
- 系统优势
- 系统局限
- 故障排查
- 常见问题解答
- 验证与测试
- 许可证

## 系统概述
本系统是一个面向高频交易场景的实时风控模块，能够处理百万级/秒的订单与成交事件，并在微秒级时间内完成规则评估与处置指令生成。系统采用分片锁、异步处理与批处理优化，规则、指标、维度与动作均可扩展。

- 高并发: 支持百万级/秒事件处理
- 低延迟: 微秒级响应（在常见硬件上 P99 约 1ms 量级）
- 可扩展: 规则、指标、动作、统计维度均为可插拔设计
- 多维统计: 支持账户、合约、产品、交易所、账户组等维度

## 需求满足情况
- 单账户成交量限制: 提供 `AccountTradeMetricLimitRule`，支持按账户/产品/合约聚合，超过阈值生成暂停交易等动作。指标可扩展为成交量、成交金额等。
- 报单频率控制: 提供 `OrderRateLimitRule`，按滑动窗口统计账户/合约/产品维度报单量，超过阈值暂停报单，回落后自动恢复。支持运行时调整阈值与窗口。
- Action 处置指令: 使用 `Action` 枚举统一表达，包括暂停/恢复账户交易、暂停/恢复报单、合约/产品维度的暂停恢复、告警、强制减仓、追加保证金等。一个规则可关联多个动作。
- 多维统计引擎: 提供 `InstrumentCatalog` 与多维计数器，支持账户、合约、产品、交易所、账户组等维度；新增维度时只需扩展键构造逻辑与映射。

## 系统架构与数据流

整体架构（来自用户手册的内容已合并）：
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

数据流程：
```
订单/成交 → 引擎接收 → 规则评估 → 统计更新 → 动作生成 → 结果返回
    ↓           ↓           ↓           ↓           ↓
  验证       并发控制     风险计算     状态同步     动作执行
```

关键设计：
- 分片锁架构: 通过 64-128 个分片降低锁竞争。
- 异步处理模型: Producer → Queue → Worker Pool → 聚合器，支持批处理与背压。
- 内存优化: 使用 `__slots__`、对象池与批处理，降低 GC 压力与抖动。
- 插件化: 规则、指标、动作、维度均可独立扩展，支持运行时更新。

目录结构：
```
risk_engine/
├── models.py              # 数据模型定义（Order、Trade、Direction）
├── engine.py              # 同步风控引擎
├── async_engine.py        # 异步高性能引擎
├── rules.py               # 规则框架与具体规则实现
├── actions.py             # 风控动作定义
├── metrics.py             # 指标类型（成交量/金额/报单/撤单）
├── dimensions.py          # 多维度统计与目录映射
├── state.py               # 状态与计数器（线程安全）
├── config.py              # 配置模型与动态规则配置
└── accel/                 # 性能加速（可选：Numba/Cython）
```

## 接口设计（模型、规则、配置）
- 数据模型：
```python
# 订单
@dataclass(slots=True)
class Order:
    oid: int
    account_id: str
    contract_id: str
    direction: Direction
    price: float
    volume: int
    timestamp: int  # 纳秒
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None

# 成交
@dataclass(slots=True)
class Trade:
    tid: int
    oid: int
    price: float
    volume: int
    timestamp: int  # 纳秒
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None
```

- 规则接口：
```python
class Rule(ABC):
    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        ...
    def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
        ...

@dataclass
class RuleResult:
    actions: List[Action]
    reasons: List[str]
```

- 配置接口：
```python
@dataclass
class VolumeLimitRuleConfig:
    threshold: float
    dimension: StatsDimension
    metric: MetricType
    reset_daily: bool = True

@dataclass
class OrderRateLimitRuleConfig:
    threshold: int
    window_seconds: Optional[int] = None
    window_ns: Optional[int] = None
    dimension: StatsDimension = StatsDimension.ACCOUNT

@dataclass
class RiskEngineConfig:
    contract_to_product: Dict[str, str]
    volume_limit: Optional[VolumeLimitRuleConfig]
    order_rate_limit: Optional[OrderRateLimitRuleConfig]
    num_shards: int = 64
    worker_threads: int = 4
```

## 核心功能说明
- 成交量/金额限制：`AccountTradeMetricLimitRule`，支持账户、合约、产品等维度汇总；超过阈值触发暂停交易、告警等动作。
- 报单频控：`OrderRateLimitRule`，滑动窗口统计订单数量，超过阈值触发暂停，回落触发恢复；阈值与窗口支持运行时更新。
- 多维统计：`InstrumentCatalog` 与多维计数器，O(1) 查询，易于新增维度（交易所、账户组等）。
- 动作去抖：对账户级暂停/恢复做状态机去抖，避免重复下发。

## 快速开始
- 安装依赖：
```bash
pip install -r requirements.txt
```
- 基本示例：
```python
from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.config import StatsDimension

config = RiskEngineConfig(
    contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
    volume_limit=VolumeLimitRuleConfig(
        threshold=1000,
        dimension=StatsDimension.PRODUCT,
        metric=MetricType.TRADE_VOLUME,
    ),
    order_rate_limit=OrderRateLimitRuleConfig(
        threshold=50,
        window_seconds=1,
        dimension=StatsDimension.ACCOUNT,
    ),
)
engine = RiskEngine(config)
```

## 详细使用指南
- 多维统计示例（按产品维度统计成交金额）：
```python
config = RiskEngineConfig(
    contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
    volume_limit=VolumeLimitRuleConfig(
        threshold=100_000_000,
        dimension=StatsDimension.PRODUCT,
        metric=MetricType.TRADE_NOTIONAL,
    ),
)
```
- 自定义规则：
```python
class CustomPriceDeviationRule(Rule):
    def __init__(self, rule_id: str, max_deviation: float):
        self.rule_id = rule_id
        self.max_deviation = max_deviation
        self.reference_prices = {}
    def on_order(self, ctx, order):
        ref = self.reference_prices.get(order.contract_id, order.price)
        dev = abs(order.price - ref) / ref
        if dev > self.max_deviation:
            return RuleResult(actions=[Action.BLOCK_ORDER, Action.ALERT], reasons=["价格偏离过大"])
        self.reference_prices[order.contract_id] = order.price
        return None
```
- 异步高性能引擎：参考 `bench_async.py` 与 `examples/benchmark.py`。
- 动态配置更新：
```python
engine.update_order_rate_limit(threshold=200, window_ns=1_000_000_000)
engine.update_volume_limit(threshold=2000)
```

## 性能验证
- 运行基准：
```bash
python bench_async.py
python bench.py
```
- 预期指标：
- 吞吐量: 大于 1,000,000 事件/秒（单机）
- 延迟: P99 约毫秒级
- 内存: 1M 事件 < 1GB

## 系统优势
- 高性能：分片锁、异步与批处理、内存优化
- 可扩展：规则/指标/动作/维度可插拔，支持热更新
- 易用：API 简洁、示例与测试完备

## 系统局限
- 单机架构：极限性能受硬件限制，需要更高容量时考虑分布式
- 内存依赖：高并发下内存占用偏高，需合理容量规划
- 规则复杂度：复杂计算建议异步化或预计算
- 持久化：未内置持久化，需结合存储实现

## 故障排查
- 延迟升高：检查 GC、锁竞争、规则计算复杂度
- 内存升高：检查统计数据规模、队列积压、对象复用
- 吞吐下降：查看 CPU、IO 等瓶颈并调整批量与分片

## 常见问题解答
- 同步还是异步引擎：中低频用同步，高频用异步
- 分片数设置：以 CPU 核心数×8~16 为起点，结合监控调优
- 规则冲突：按添加顺序执行，必要时实现优先级

## 验证与测试
- 运行全部测试：
```bash
# 首选
python -m pytest tests -v
# 若环境无 pytest，可运行核心单元测试
python -m unittest tests/test_engine.py -v
```
- 示例与压力：
```bash
python examples/benchmark.py
python examples/performance_validation.py
python examples/complete_demo.py
python examples/simulate.py
```

## 许可证
本项目采用 MIT 许可证。

