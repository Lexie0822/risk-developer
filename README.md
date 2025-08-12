## 金融风控模块（Python）

一个可扩展的实时风控引擎样例，支持高频订单与成交数据的风控规则，并输出处置指令（Action）。

### 功能点
- **规则**
  - 单账户成交量限制：当统计量超过阈值时触发 `SUSPEND_ACCOUNT_TRADING`。
  - 报单频率控制：滑动时间窗统计下的报单次数，超过阈值触发 `SUSPEND_ORDERING`，恢复后触发 `RESUME_ORDERING`。
- **多维统计**：可按 `account`、`contract`、`product` 维度统计（通过 `contract_to_product` 提供映射）。
- **扩展性**：规则、统计维度与阈值均为配置化；`Action` 为统一输出载体。

### 安装与运行
无需第三方依赖（Python 3.10+）。

```bash
python -m examples.simulate
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
- 演示版本为单进程内存态，不具备持久化与分布式一致性保障。
- 未实现真正的微秒级响应与百万级 QPS；需要配合多进程分片/异步 IO/更底层语言优化。
- 未实现风控状态持久化与跨日自动重置（可在生产中通过定时器/数据库实现）。

### 目录
- `risk_engine/models.py`：订单、成交、方向、产品解析
- `risk_engine/actions.py`：Action 定义
- `risk_engine/stats.py`：多维统计引擎
- `risk_engine/rules.py`：风控规则实现
- `risk_engine/engine.py`：引擎装配与消息入口
- `examples/simulate.py`：示例脚本
