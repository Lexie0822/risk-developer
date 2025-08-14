## 金融风控模块系统

### 目录
- 系统概述
- 系统架构
- 数据流程
- 核心设计原则
- 核心组件说明
- 接口设计
- 规则实现说明
- 快速开始
- 示例与测试
- 性能验证
- 最佳实践
- 故障排查
- 系统优势
- 系统局限
- 许可证

## 系统概述

本系统是一个高性能的实时金融风控模块，专为高频交易场景设计。系统采用分片锁架构、异步处理与批处理优化，能处理百万级/秒的订单与成交事件，并在微秒级时间内完成规则评估与处置指令生成。

### 满足的核心需求
- 单账户成交量限制：支持在账户/合约/产品等维度统计当日指标，超阈暂停交易。
- 报单频率控制：支持滑动时间窗口频控，超阈暂停报单，回落自动恢复。
- Action 处置：统一的动作枚举，支持同一规则关联多个动作。
- 多维统计引擎：支持账户、合约、产品、交易所、账户组等维度，易于扩展。

## 系统架构

```
risk_engine/
├── models.py              # 数据模型定义（Order、Trade、Direction）
├── engine.py              # 同步风控引擎
├── async_engine.py        # 异步高性能引擎
├── rules.py               # 规则框架与具体规则
├── actions.py             # 处置动作定义
├── metrics.py             # 指标类型（可扩展）
├── dimensions.py          # 多维度统计与目录
├── state.py               # 统计与滑窗计数（线程安全）
├── config.py              # 规则/引擎配置与动态规则
└── stats.py               # 兼容测试的维度枚举
```

### 整体架构（来自用户手册，保留）
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

## 数据流程（保留）
```
订单/成交 → 引擎接收 → 规则评估 → 统计更新 → 动作生成 → 结果返回
    ↓           ↓           ↓           ↓           ↓
  验证      并发控制    风险计算    状态同步    动作执行
```

## 核心设计原则
- 分片锁架构：使用 64–128 个分片降低锁竞争。
- 异步处理：支持高并发事件处理（详见 `async_engine.py`）。
- 批处理优化：批量处理提高吞吐量。
- 内存优化：使用 `slots=True` 和轻量结构降低开销。
- 插件化设计：规则、指标、动作均可独立扩展。

## 核心组件说明（精选）
- 风控引擎（RiskEngine/AsyncRiskEngine）：处理订单与成交事件，协调规则执行。
- 规则引擎（rules）：`AccountTradeMetricLimitRule`、`OrderRateLimitRule` 等；支持自定义规则。
- 状态管理（state）：`MultiDimDailyCounter` 按日+维度聚合，`RollingWindowCounter` 滑窗计数。
- 动作处理（actions）：`Action` 枚举与动作下发；内置去抖逻辑避免重复下发。
- 多维目录（dimensions）：`InstrumentCatalog` 用于合约→产品/交易所映射，O(1) 查询。

## 接口设计

### 数据模型
```python
from dataclasses import dataclass
from typing import Optional
from risk_engine.models import Direction

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

@dataclass(slots=True)
class Trade:
    tid: int
    oid: int
    price: float
    volume: int
    timestamp: int  # 纳秒
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
```

### 规则接口
```python
from dataclasses import dataclass
from typing import List, Optional
from risk_engine.actions import Action

@dataclass(slots=True)
class RuleResult:
    actions: List[Action]
    reasons: List[str]

class Rule:
    rule_id: str
    def on_order(self, ctx, order) -> Optional[RuleResult]: ...
    def on_trade(self, ctx, trade) -> Optional[RuleResult]: ...
```

### 配置接口（可扩展）
```python
from dataclasses import dataclass
from typing import Dict, Optional
from risk_engine.metrics import MetricType
from risk_engine.stats import StatsDimension

@dataclass
class VolumeLimitRuleConfig:
    threshold: float
    dimension: StatsDimension = StatsDimension.PRODUCT
    reset_daily: bool = True
    metric: MetricType = MetricType.TRADE_VOLUME

@dataclass
class OrderRateLimitRuleConfig:
    threshold: int
    window_ns: Optional[int] = None
    window_seconds: Optional[int] = None
    dimension: StatsDimension = StatsDimension.ACCOUNT

@dataclass
class RiskEngineConfig:
    contract_to_product: Dict[str, str]
    contract_to_exchange: Dict[str, str] = None
    volume_limit: Optional[VolumeLimitRuleConfig] = None
    order_rate_limit: Optional[OrderRateLimitRuleConfig] = None
    num_shards: int = 64
    worker_threads: int = 4
```

## 规则实现说明
- 成交量限制（AccountTradeMetricLimitRule）
  - 指标：成交量、成交金额、报单量等。
  - 维度：账户/合约/产品/交易所/账户组任意组合。
  - 触发：超阈产生一个或多个配置的 Action。
- 报单频控（OrderRateLimitRule）
  - 滑动窗口按秒计数，支持动态调整阈值与窗口大小。
  - 超阈触发暂停，计数回落自动恢复（配合去抖避免重复）。
- 多维统计引擎
  - `MultiDimDailyCounter`：日级多维累加；`RollingWindowCounter`：秒级滑窗计数。

## 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 基本示例
```python
from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.stats import StatsDimension

config = RiskEngineConfig(
    contract_to_product={
        "T2303": "T10Y",
        "T2306": "T10Y",
    },
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

order = Order(1, "ACC_001", "T2303", Direction.BID, 100.5, 10, 1_700_000_000_000_000_000)
engine.on_order(order)
trade = Trade(1, 1, 100.5, 10, 1_700_000_000_000_000_000, account_id="ACC_001", contract_id="T2303")
engine.on_trade(trade)
```

### 自定义规则示例
```python
from risk_engine.rules import Rule, RuleResult
from risk_engine.actions import Action

class CustomPriceDeviationRule(Rule):
    def __init__(self, rule_id: str, max_dev: float):
        self.rule_id = rule_id
        self.max_dev = max_dev
        self.ref = {}
    def on_order(self, ctx, order):
        ref = self.ref.get(order.contract_id, order.price)
        dev = abs(order.price - ref) / ref
        if dev > self.max_dev:
            return RuleResult(actions=[Action.BLOCK_ORDER, Action.ALERT], reasons=[f"价格偏离{dev:.2%}超过阈值"])
        self.ref[order.contract_id] = order.price
        return None

engine.add_rule(CustomPriceDeviationRule("PRICE_CHECK", 0.05))
```

## 示例与测试
- 单元测试位于 `tests/`。可任选以下方式运行：
```bash
# 使用 unittest（通用）
python -m unittest discover -s tests -v

# 或使用 pytest（若环境可用）
pytest -q tests
```
- 运行示例：
```bash
python examples/complete_demo.py
```

## 性能验证
```bash
# 异步引擎基准（推荐）
python bench_async.py

# 基础引擎基准
python bench.py
```
预期指标：吞吐量 > 1,000,000 事件/秒；延迟 P99 < 1,000 微秒。

## 最佳实践（精选）
- 合理设置分片数：CPU 核心数 × 8–16 作为起点。
- 高频场景使用异步引擎，并尽量批量提交事件。
- 规则尽量保持无状态，状态统一交由 `state` 维护。
- 根据监控持续调优阈值、窗口与批量大小。

## 故障排查（精选）
- 延迟增大：检查 GC、锁竞争与规则复杂度。
- 内存上升：检查统计数据体量与队列积压。
- 吞吐下降：确认 CPU 利用率、I/O 阻塞与配置。

## 系统优势
- 高性能：分片锁、异步处理、批处理与内存优化。
- 可扩展：插件化规则、灵活指标、可扩维度与动态配置。
- 易用性：简洁 API、丰富示例与完善文档。

## 系统局限
- 单机部署：性能受硬件限制；更高性能需分布式。
- 内存依赖：高并发下需要充足内存。
- 复杂规则：建议异步化或预计算以降低延迟影响。
- 持久化：当前未内置持久化，重启需重新加载状态/快照。

## 许可证
本项目采用 MIT 许可证。

