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
```

### 多进程分片示例
```bash
python3 -m examples.mp_shard
```

### 设计要点（高并发/低延迟）
- 数据模型采用 `dataclass(slots=True)` 减少对象开销。
- 频控使用无锁 `deque` 实现滑动时间窗；只在当前 key 上清理过期事件，时间复杂度均摊 O(1)。
- 多维统计使用扁平 tuple key 的哈希表，O(1) 读写，便于扩展维度。
- 规则解耦：独立计算、独立状态，便于横向扩展与分区（按 `account_id` 分片）。

### 优势
- 简洁、可读、易扩展的规则与统计抽象。
- 统一 `Action` 输出，便于下游撮合/交易系统接入。
- 零依赖、可直接在标准 Python 环境运行。

### 局限
- 当前是单进程内存态，不具备持久化与分布式一致性。
- 未实现微秒级响应与百万级 QPS。目前project的演示关注架构可扩展性与可验证性，性能可通过下述路径演进：
  - 进程级分片（已提供 `examples/mp_shard.py`），按 `account_id`/`client_id` 一致性哈希，横向扩容 N 倍；
  - 异步 IO/批处理：合并多条事件一次处理，减少函数/结构体分配；
  - 热路径下沉：将规则核⼼计数迁移到 C/Rust（Cython、pyo3），实现无锁 ring-buffer；
  - CPU 亲和/NUMA 绑定与 pin 线程，减少调度抖动；
  - 序列化零拷贝（共享内存/`mmap`/`pyarrow Plasma`）对接撮合与行情。
- 状态持久化与跨日：
  - 将 `snapshot()` 输出写入 Redis/RocksDB，并在进程启动时 `restore()`；
  - 通过定时器或由撮合的“交易日切换”事件驱动跨日重置；
  - 引入版本化阈值配置，支持灰度与回滚。
- 可靠性：
  - 引入断路器与幂等处置（`Action` 去重、有效期 `until_ns`）；
  - 通过审计日志（append-only）保证可追溯。


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
