# 金融风控模块（单一权威文档）

一个用于高频交易场景的实时风控模块，处理百万级/秒的订单与成交事件，微秒级完成规则评估与处置指令（Action）生成。

## 1. 接口设计（可配置、可扩展）

- 规则与动作：
  - 动作 `Action` 为枚举，支持暂停/恢复报单、暂停/恢复账户交易等，便于扩展与去重投递。
  - 规则 `Rule` 基类统一 `on_order`/`on_trade` 接口；已实现两类规则：
    - 单账户成交量（或金额）阈值限制：`AccountTradeMetricLimitRule`
    - 报单频率限制（滑动窗口）：`OrderRateLimitRule`
- 配置入口：
```python
from risk_engine import RiskEngine, EngineConfig
from risk_engine.config import (
    RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig,
)
from risk_engine.stats import StatsDimension
from risk_engine.metrics import MetricType
```
- 规则配置结构：
```python
# 成交量/金额等阈值限制
VolumeLimitRuleConfig(
    threshold=1000,                        # 阈值（手/金额等）
    dimension=StatsDimension.PRODUCT,      # ACCOUNT | CONTRACT | PRODUCT
    reset_daily=True,                      # 是否按自然日重置
    metric=MetricType.TRADE_VOLUME,        # TRADE_VOLUME / TRADE_NOTIONAL ...
)

# 报单频率限制（兼容两种窗口参数）
OrderRateLimitRuleConfig(
    threshold=50,                          # 次/窗口
    window_seconds=1,                      # 窗口秒数（推荐）
    # window_ns=1_000_000_000,            # 兼容：纳秒窗口（可选，若提供则覆盖 window_seconds）
    dimension=StatsDimension.ACCOUNT,      # ACCOUNT | CONTRACT | PRODUCT
)

# 引擎配置（简化）
RiskEngineConfig(
    contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},  # 合约→产品
    volume_limit=...,                       # 按需开启
    order_rate_limit=...,                   # 按需开启
)
```

## 2. 输入数据定义（纳秒级时间戳）

```python
from dataclasses import dataclass
from enum import Enum

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
    timestamp: int  # ns

@dataclass(slots=True)
class Trade:
    tid: int
    oid: int
    price: float
    volume: int
    timestamp: int  # ns
    # 兼容：若未填，系统将基于 oid 用最近订单补全 account_id/contract_id
    account_id: str | None = None
    contract_id: str | None = None
```

## 3. 系统开发与用法

- 核心引擎：`RiskEngine`（同步）与 `AsyncRiskEngine`（异步高性能）。
- 处置指令：通过回调 `action_sink(Action, rule_id, obj)` 发出；默认打印，可对接消息总线。

```python
from risk_engine import RiskEngine, EngineConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.actions import Action
from risk_engine.metrics import MetricType
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule

engine = RiskEngine(
    EngineConfig(contract_to_product={"T2303": "T10Y"}),
    rules=[
        AccountTradeMetricLimitRule(
            rule_id="VOL-1000",
            metric=MetricType.TRADE_VOLUME,
            threshold=1000,
        ),
        OrderRateLimitRule(
            rule_id="ORDER-50-1S",
            threshold=50,
            window_seconds=1,
        ),
    ],
)

ts = 1_700_000_000_000_000_000
engine.on_order(Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts))
engine.on_trade(Trade(1, 1, 100.0, 1000, ts + 1))
```

- 异步版本示例：
```python
import asyncio
from risk_engine.async_engine import create_async_engine
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.stats import StatsDimension

async def main():
    cfg = RiskEngineConfig(
        contract_to_product={"T2303": "T10Y"},
        volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=StatsDimension.PRODUCT),
    )
    engine = create_async_engine(cfg)
    await engine.start()
    try:
        ...  # await engine.submit_order(...); await engine.submit_trade(...)
    finally:
        await engine.stop()

asyncio.run(main())
```

## 4. 如何运行测试

无需额外依赖，直接使用标准库 unittest：
```bash
python3 -m unittest discover -v
```

## 5. 性能与并发

- 目标：吞吐 1,000,000 事件/秒；P99 延迟 < 1,000 微秒。
- 关键手段：分片锁 `ShardedLockDict`、O(1) 路径、多维按日计数器、滑动窗口计数器、异步+批处理。
- 可选基准：
```bash
python bench_async.py
python bench.py
```

## 6. 多维统计与扩展

- 维度：账户、合约、产品（可扩展交易所、账户组）。
- 产品聚合：通过 `contract_to_product` 将 T2303/T2306 等汇总为同一产品统计。
- 新增维度/指标/动作：分别扩展 `dimensions.py`、`metrics.py`、`actions.py`，或新增自定义 `Rule`。

## 7. 优势与局限

- 优势：
  - 高并发/低延迟设计；面向金融实时场景。
  - 规则/维度/指标模块化，配置驱动与热更新。
  - 纳秒时间戳、轻量 `dataclass(slots=True)`，降低 GC 压力。
- 局限：
  - 当前为单机引擎，如需更高吞吐需引入分布式/多进程分片。
  - 主要聚焦实时处理，历史分析与 ML 策略不在本版本范围。

## 8. 目录速览

```
risk_engine/
├── engine.py          # 同步引擎
├── async_engine.py    # 异步引擎
├── rules.py           # 规则实现
├── actions.py         # 动作枚举
├── models.py          # Order/Trade/Direction
├── metrics.py         # 指标类型
├── dimensions.py      # 维度键与目录
├── state.py           # 计数器与分片存储
└── stats.py           # 旧版维度枚举（兼容）
```

本 README 为唯一权威文档，覆盖接口设计、输入定义、用法/测试、优势与局限，符合题目交付要求。

