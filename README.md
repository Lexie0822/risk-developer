# 金融风控模块系统

## 1. 背景与目标
设计一个用于高频交易场景的实时风控模块，处理高并发订单（Order）与成交（Trade）事件，动态触发风控规则并生成处置指令（Action）。目标：
- 高并发：百万级事件/秒
- 低延迟：微秒级响应
- 可扩展：规则、指标、统计维度、动作均可扩展

本仓库包含完整引擎代码、规则实现、示例与测试用例，可直接用于笔试与本地验证。

---

## 2. 输入数据定义
- Order
  - `oid: uint64_t` 订单唯一标识符
  - `account_id: string` 交易账户编号
  - `contract_id: string` 合约代码（如 T2303）
  - `direction: enum` 买卖方向（Bid/Ask）
  - `price: double` 订单价格
  - `volume: int32_t` 订单数量
  - `timestamp: uint64_t` 纳秒时间戳
- Trade
  - `tid: uint64_t` 成交唯一标识符
  - `oid: uint64_t` 关联订单ID
  - `price: double` 成交价格
  - `volume: int32_t` 实际成交量
  - `timestamp: uint64_t` 纳秒时间戳

代码模型：
```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class Direction(str, Enum):
    BID = "Bid"
    ASK = "Ask"

@dataclass(slots=True)
class Order:
    oid: int
    account_id: str
    contract_id: str
    direction: Direction
    price: float
    volume: int
    timestamp: int
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None

@dataclass(slots=True)
class Trade:
    tid: int
    oid: int
    price: float
    volume: int
    timestamp: int
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None
```

---

## 3. 接口与配置设计（满足题目“接口设计”要求）
核心配置均为显式数据类，便于声明式配置与扩展：

```python
from dataclasses import dataclass
from enum import Enum
from risk_engine.metrics import MetricType

class StatsDimension(str, Enum):
    ACCOUNT = "account"
    CONTRACT = "contract"
    PRODUCT = "product"
    EXCHANGE = "exchange"
    ACCOUNT_GROUP = "account_group"

@dataclass
class VolumeLimitRuleConfig:
    threshold: float
    dimension: StatsDimension = StatsDimension.PRODUCT
    reset_daily: bool = True
    metric: MetricType = MetricType.TRADE_VOLUME  # 成交量 / 成交金额等

@dataclass
class OrderRateLimitRuleConfig:
    threshold: int
    window_ns: int | None = None
    window_seconds: int | None = None
    dimension: StatsDimension = StatsDimension.ACCOUNT

@dataclass
class RiskEngineConfig:
    contract_to_product: dict[str, str]
    contract_to_exchange: dict[str, str] | None = None
    volume_limit: VolumeLimitRuleConfig | None = None
    order_rate_limit: OrderRateLimitRuleConfig | None = None
```

- 成交量限制（账户/合约/产品维度；指标可选成交量、成交金额等）
- 报单频控（滑动窗口，支持动态调整阈值与窗口；自动恢复）
- 一个规则可关联多个动作类型（暂停账户交易、暂停报单、告警等）
- 可扩展：新增指标类型、统计维度、动作类型与自定义规则类

---

## 4. 核心实现与扩展点（满足题目“系统开发”要求）
- 规则基类与上下文：`risk_engine.rules.Rule`、`RuleContext`、`RuleResult`
- 内置规则：
  - `AccountTradeMetricLimitRule`：按日指标阈值限制（成交量/成交金额/报单量）
  - `OrderRateLimitRule`：报单频率滑动窗口限制（账户/合约/产品维度）
- 动作定义：`risk_engine.actions.Action`（暂停/恢复、告警、精细化拦截等）
- 多维统计：`risk_engine.state.MultiDimDailyCounter` 支持账户、合约、产品、交易所、账户组等维度；`InstrumentCatalog` 支持合约到产品映射
- 引擎：`risk_engine.engine.RiskEngine` 支持规则集合、去抖的动作下发、快照/恢复

自定义规则示例：
```python
from risk_engine.rules import Rule, RuleResult
from risk_engine.actions import Action
from risk_engine.models import Order

class PriceDeviationRule(Rule):
    def __init__(self, rule_id: str, max_dev: float):
        self.rule_id = rule_id
        self.max_dev = max_dev
        self.ref = {}

    def on_order(self, ctx, order: Order):
        p0 = self.ref.get(order.contract_id, order.price)
        dev = abs(order.price - p0) / max(p0, 1e-12)
        self.ref[order.contract_id] = order.price
        if dev > self.max_dev:
            return RuleResult(actions=[Action.BLOCK_ORDER], reasons=[f"deviation {dev:.2%}>"])
        return None
```

---

## 5. 快速开始
- 安装依赖
```bash
python3 -m pip install -r requirements.txt
```
- 最小可运行示例
```python
from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, StatsDimension
from risk_engine.metrics import MetricType
from risk_engine.models import Order, Trade, Direction

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

order = Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 1, 1)
engine.on_order(order)
trade = Trade(1, 1, 100.0, 1, 2, account_id="ACC_001", contract_id="T2303")
engine.on_trade(trade)
```

---

## 6. 示例与测试
- 示例程序：`examples/basic_usage.py`、`examples/complete_demo.py`
- 基准测试：`bench.py`、`bench_async.py`
- 运行测试：
```bash
python3 -m pytest -q tests
```

---

## 7. 性能与架构概览
- 分片锁与轻量对象，降低锁竞争与内存占用
- 窗口计数器与按日多维计数，常量时间路径
- 可选异步引擎与批处理，提高吞吐量

---

## 8. 优势
- 高并发、低延迟，接口简洁
- 多维统计与规则/动作/指标可插拔扩展
- 示例与测试齐全，便于验证

## 9. 局限
- 当前为单机内存型状态，未包含分布式与持久化
- 复杂规则需谨慎控制计算量

---

## 10. 与题目对照清单（自检）
- 单账户成交量限制：已实现（支持成交量/金额，账户/合约/产品维度，可扩展）
- 报单频率控制：已实现（滑动窗口，动态阈值/窗口，自动恢复）
- Action：已枚举并可扩展；单规则可发多个动作
- 多维统计：已支持合约与产品，扩展到交易所、账户组等
- 接口设计：配置数据类与规则接口已给出，并含自定义示例
- 系统开发：完整Python引擎与规则实现、示例、测试
- 系统文档：本 README 即用户+技术文档，包含用法、优势与局限

---

## 许可证
MIT

