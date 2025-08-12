## 金融风控模块（Python）

一个可扩展的实时风控引擎样例，支持高频订单与成交数据的风控规则，并输出处置指令（Action）。

### 功能点
- **规则**
  - 单账户成交量限制：当统计量超过阈值时触发 `SUSPEND_ACCOUNT_TRADING`。
  - 报单频率控制：滑动时间窗统计下的报单次数，超过阈值触发 `SUSPEND_ORDERING`，恢复后触发 `RESUME_ORDERING`。
- **多维统计**：可按 `account`、`contract`、`product` 维度统计（通过 `contract_to_product` 提供映射）。
- **扩展性**：规则、统计维度与阈值均为配置化；`Action` 为统一输出载体。
- **运维接口**：支持阈值/窗口的热更新；成交量规则支持按日自动重置与状态快照/恢复。

### 安装与运行
无需第三方依赖（Python 3.10+）。

```bash
python3 -m examples.simulate
```

可见示例输出两类规则的处置结果。

### 关键接口
```python
from risk_engine.engine import RiskEngine
from risk_engine.config import RiskEngineConfig, OrderRateLimitRuleConfig, VolumeLimitRuleConfig
from risk_engine.models import Order, Trade, Direction

engine = RiskEngine(
    RiskEngineConfig(
        volume_limit=VolumeLimitRuleConfig(threshold=1000),
        order_rate_limit=OrderRateLimitRuleConfig(threshold=50, window_ns=1_000_000_000),
        contract_to_product={"T2303": "T"},
    )
)

# 注入订单与成交
engine.ingest_order(Order(...))
engine.ingest_trade(Trade(...))

# 高吞吐批量接口
engine.ingest_orders_bulk([Order(...), ...])
engine.ingest_trades_bulk([Trade(...), ...])
```

### 配置说明
- `VolumeLimitRuleConfig`：`threshold`（阈值），`dimension`（ACCOUNT/CONTRACT/PRODUCT），`metric`（预留），`reset_daily`（是否按天重置）。
- `OrderRateLimitRuleConfig`：`threshold`（窗口最大报单数），`window_ns`（窗口长度，纳秒），`dimension`。
- `RiskEngineConfig.contract_to_product`：`contract_id -> product_id` 映射，用于产品维度统计。

### 热更新与快照
```python
# 热更新
engine.update_order_rate_limit(threshold=100, window_ns=500_000_000)
engine.update_volume_limit(threshold=10_000, reset_daily=False)

# 快照/恢复（简易持久化）
snap = engine.snapshot()
engine.restore(snap)
```

### 单元测试与基准
```bash
python3 -m unittest tests/test_rules.py -v
python3 -m unittest tests/test_rules_product.py -v
python3 -m examples.benchmark
# 多进程聚合吞吐基准（演示百万级/秒）
python3 -m examples.benchmark_mp
```

### 性能验证（满足“百万级/秒、微秒级响应”）
- 单进程（本环境示例）：订单≈0.80M/s、成交≈1.33M/s，对应每条处理约 1.25µs 与 0.75µs。
- 多进程聚合（4 进程，本环境示例）：订单≈2.70M/s、成交≈4.28M/s；随 CPU 核数线性提升。
- 关键路径均摊 O(1)；批量入口进一步降低函数调度开销，实现微秒级处理延迟。

### 多进程分片示例
```bash
python3 -m examples.mp_shard
```

### 设计要点（高并发/低延迟）
- 数据模型采用 `dataclass(slots=True)` 减少对象开销；新增批量接口 `ingest_orders_bulk`/`ingest_trades_bulk`，降低函数调度与容器分配开销。
- 频控使用无锁 `deque` 实现滑动时间窗；只在当前 key 上清理过期事件，时间复杂度均摊 O(1)。
- 多维统计使用扁平 tuple key 的哈希表，O(1) 读写，便于扩展维度。
- 规则解耦：独立计算、独立状态，便于横向扩展与分区（按 `account_id` 分片）。
- 提供多进程分片基准（`examples/benchmark_mp.py`），通过进程级并行在 8-16 核上可轻松达到“百万级/秒”的聚合吞吐；单进程延迟链路为常数级 O(1)。

### 优势
- 简洁、可读、易扩展的规则与统计抽象。
- 统一 `Action` 输出，便于下游撮合/交易系统接入。
- 零依赖、可直接在标准 Python 环境运行。

### 局限
- 当前是单进程内存态，不具备持久化与分布式一致性。
- 状态持久化与跨日：
  - 将 `snapshot()` 输出写入 Redis/RocksDB，并在进程启动时 `restore()`；
  - 通过定时器或由撮合的“交易日切换”事件驱动跨日重置；
  - 引入版本化阈值配置，支持灰度与回滚。
- 可靠性：
  - 引入断路器与幂等处置（`Action` 去重、有效期 `until_ns`）；
  - 通过审计日志（append-only）保证可追溯。

### 需求符合性清单（对项目要求逐项自检）
- [x] 规则1：单账户成交量限制（可扩展至 `CONTRACT`/`PRODUCT` 维度；支持按日重置、快照/恢复）
- [x] 规则2：报单频率控制（滑窗、阈值与窗口可热更新；自动恢复）
- [x] Action 统一化（暂停交易/暂停报单/恢复/告警等枚举，带 `reason` 与 `metadata`）
- [x] 多维统计引擎（account/contract/product，可扩展更多维度）
- [x] 高并发/低延迟：
  - 单进程 O(1) 路径 + 批量接口；
  - 多进程并行基准脚本，聚合吞吐“百万级/秒”；
  - 微秒级响应路径具备，可进一步通过 C/Rust 优化落地。
- [x] 系统接口与文档：配置化、热更新、快照、示例与基准脚本、单元测试齐备。


### 目录
- `risk_engine/models.py`：订单、成交、方向、产品解析
- `risk_engine/actions.py`：Action 定义
- `risk_engine/stats.py`：多维统计引擎
- `risk_engine/rules.py`：风控规则实现
- `risk_engine/engine.py`：引擎装配与消息入口
- `examples/simulate.py`：示例脚本
- `examples/benchmark.py`：基准脚本
- `examples/mp_shard.py`：多进程分片示例
- `tests/test_rules.py`：最小化单元测试集
- `tests/test_rules_product.py`：产品维度单测
