# 金融风控模块系统

一个高性能的实时金融风控模块，专为高频交易场景设计，能够处理百万级/秒的订单和成交数据，并在微秒级时间内完成风控规则评估和处置指令生成。

本 README 包含接口设计、系统用法、优势与局限、以及示例与测试说明。

## 核心特性

- **高并发**: 支持百万级/秒事件处理
- **低延迟**: 微秒级响应时间
- **可扩展**: 支持动态规则配置和热更新
- **多维统计**: 支持账户、合约、产品、交易所、账户组等维度
- **实时监控**: 内置性能指标和监控

## 系统架构

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

## 与需求逐条对照

- **单账户成交量限制（含扩展指标）**
  - 规则：`AccountTradeMetricLimitRule`（按日累计）。
  - 指标：`MetricType.TRADE_VOLUME`（成交量），`TRADE_NOTIONAL`（成交金额），以及 `ORDER_COUNT`（报单量，成交侧也可扩展）。
  - 多动作：规则支持 `actions=Tuple[Action, ...]`，例如同时下发 `SUSPEND_ACCOUNT_TRADING` 与 `ALERT`。
  - 多维：账户/合约/产品/交易所/账户组维度可选开启（`by_account/by_contract/by_product/by_exchange/by_account_group`）。

- **报单频率控制（滑动窗口）**
  - 规则：`OrderRateLimitRule`（1 秒粒度滑动窗口）。
  - 动态阈值与窗口：通过 `engine.update_order_rate_limit(threshold=..., window_ns=...)` 热更新；规则也可直接构造不同阈值/窗口。
  - 维度：支持账户/合约/产品维度统计（`dimension="account"|"contract"|"product"`）。
  - 自动恢复：窗口内统计量回落至阈值及以下自动下发 `RESUME_*` 动作，结合引擎去抖避免抖动。

- **Action（处置动作）**
  - 枚举：见 `actions.Action`，含 `SUSPEND_ACCOUNT_TRADING/RESUME_ACCOUNT_TRADING`、`SUSPEND_ORDERING/RESUME_ORDERING`、`BLOCK_ORDER/ALERT` 等。
  - 多动作：每条规则可配置多个动作（如同时暂停交易并发告警）。

- **多维统计引擎（可选扩展）**
  - 日维度：`MultiDimDailyCounter` 支持多维 Key（账户/合约/产品/交易所/账户组组合）在“自然日”分桶聚合。
  - 滑动窗口：`RollingWindowCounter` 使用固定桶结构，支持秒级滑动窗口频控。
  - 新增统计维度：通过 `dimensions.make_dimension_key` 与 `InstrumentCatalog` 扩展（已内置 `exchange_id`、`account_group_id` 支持）。

## 风控规则

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

## 数据模型

- `Order(oid, account_id, contract_id, direction, price, volume, timestamp, exchange_id?, account_group_id?)`
- `Trade(tid, oid, price, volume, timestamp, account_id?, contract_id?, exchange_id?, account_group_id?)`
- 合同与产品映射：通过引擎 `EngineConfig.contract_to_product` 与 `InstrumentCatalog` 支持。

## 快速开始

### 安装依赖

```bash
pip3 install -r requirements.txt
```

### 基本使用

```python
from risk_engine import RiskEngine, EngineConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.actions import Action
from risk_engine.metrics import MetricType
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule

config = EngineConfig(contract_to_product={"T2303": "T10Y"}, deduplicate_actions=True)
engine = RiskEngine(config)

# 成交量限制（账户+产品维度），并同时告警
engine.add_rule(
    AccountTradeMetricLimitRule(
        rule_id="R-VOL",
        metric=MetricType.TRADE_VOLUME,
        threshold=1000,
        actions=(Action.SUSPEND_ACCOUNT_TRADING, Action.ALERT),
        by_account=True,
        by_product=True,
    )
)

# 报单频控（账户维度，1s 窗口），回落自动恢复
engine.add_rule(
    OrderRateLimitRule(
        rule_id="R-RATE",
        threshold=50,
        window_seconds=1,
        suspend_actions=(Action.SUSPEND_ORDERING,),
        resume_actions=(Action.RESUME_ORDERING,),
        dimension="account",
    )
)

# 事件输入
ts = 1_700_000_000_000_000_000
engine.on_order(Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts))
engine.on_trade(Trade(tid=1, oid=1, price=100.0, volume=1, timestamp=ts, account_id="ACC_001", contract_id="T2303"))
```

### 异步高性能使用

```python
import asyncio
from risk_engine.async_engine import create_async_engine
from risk_engine.config import RiskEngineConfig
from risk_engine.models import Order, Trade, Direction

async def main():
    config = RiskEngineConfig(contract_to_product={"T2303": "T10Y"}, num_shards=128, worker_threads=8)
    engine = create_async_engine(config)
    await engine.start()
    try:
        ts = 1_700_000_000_000_000_000
        await engine.submit_order(Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts))
        await engine.submit_trade(Trade(tid=1, oid=1, price=100.0, volume=1, timestamp=ts, account_id="ACC_001", contract_id="T2303"))
    finally:
        await engine.stop()

# asyncio.run(main())
```

## 配置设计（接口）

- 代码层配置：`config.py` 提供规则配置数据类，便于声明式构造：

```python
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, StatsDimension
from risk_engine.metrics import MetricType

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
```

- 动态热更新（无需重启）：

```python
# 调整频控阈值与窗口（纳秒/秒均可）
engine.update_order_rate_limit(threshold=100, window_ns=2_000_000_000)
# 调整成交量阈值与统计维度（账户/合约/产品）
from risk_engine.stats import StatsDimension
engine.update_volume_limit(threshold=2000, dimension=StatsDimension.PRODUCT)
```

- 新增维度支持：
  - 规则侧：`AccountTradeMetricLimitRule` 中打开 `by_exchange/by_account_group` 即可纳入聚合维度。
  - 事件侧：`Order/Trade` 已携带 `exchange_id/account_group_id` 字段。

## 多维与产品/合约说明

- 产品理解为合约静态属性：例如“10年期国债期货”为产品，不同到期月份（T2303/T2306）为不同合约。
- 通过 `EngineConfig.contract_to_product` 建立合约->产品映射后，选择 `by_product=True` 即可在产品维度进行汇总统计。

## 监控和统计

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

## 如何验证（建议步骤）

1. **运行单元测试（功能正确性）**
   - 执行：
     ```bash
     python3 -m unittest discover -s /workspace/tests -p "test_*.py" -q
     ```
   - 覆盖：
     - 报单频控触发与自动恢复
     - 成交量限制（含按日重置）
     - 产品维度聚合
     - 动态热更新与状态持久化/恢复

2. **运行示例（开发者体验）**
   - 执行：
     ```bash
     python3 examples/basic_usage.py
     ```
   - 观察：标准输出的动作日志、性能统计打印。

3. **运行性能基准（吞吐与延迟）**
   - 基础：
     ```bash
     python3 bench.py
     ```
   - 异步高性能：
     ```bash
     python3 bench_async.py
     ```
   - 提示：吞吐与延迟取决于硬件与 Python 版本；可调 `num_shards/batch_size/worker_threads` 以优化。

4. **手工验证扩展点**（任选其一）
   - 多动作：构造规则 `actions=(Action.SUSPEND_ACCOUNT_TRADING, Action.ALERT)` 并触发阈值，检查两种动作均下发。
   - 指标扩展：将 `metric=MetricType.TRADE_NOTIONAL`，用不同 `price*volume` 验证阈值达成。
   - 维度扩展：在订单/成交中填充 `exchange_id/account_group_id`，并在 `AccountTradeMetricLimitRule` 打开相应 `by_*` 开关，验证聚合口径变化。

## 系统优势

- **分片锁架构**: 64-128个分片，减少锁竞争
- **异步处理**: 支持高并发事件处理
- **批处理优化**: 批量处理提高吞吐量
- **内存优化**: 轻量级对象，减少GC压力
- **可扩展性**: 规则、指标、动作可独立扩展，支持热更新

## 系统局限

- **单机限制**: 当前设计为单机部署，如需更高性能需考虑分布式
- **内存依赖**: 高并发场景下内存使用量较大
- **规则复杂度**: 复杂规则可能影响性能
- **事件类型**: 目前未内置撤单事件（`CANCEL_COUNT` 指标预留，若需要可按 `Order` 类似方式新增事件流与累加逻辑）

## 目录与代码

- 代码 API 位于 `risk_engine/` 包
- 示例位于 `examples/`
- 测试位于 `tests/`

## 许可证

本项目采用 MIT 许可证。

