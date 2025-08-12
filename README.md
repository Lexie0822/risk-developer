# 实时风控引擎（Python）

本项目实现一套面向期货/衍生品交易场景的实时风控引擎，支持高并发事件处理、低延迟判断、多维指标统计与动态规则配置。所有代码注释为中文，便于阅读与维护。

## 功能特性
- 多规则：
  - 单账户日成交量/成交金额/报单量/撤单量限制（可配置维度：账户/合约/产品/交易所/账户组任意组合）。
  - 报单频控：按 1s/60s 可调窗口进行频率控制，超过阈值暂停，回落自动恢复；阈值与时间窗可动态调整。
- 多维统计：
  - 多维日累加器 `MultiDimDailyCounter`，支持产品维度（合约归并）与拓展维度。
- 动作系统：
  - `Action` 枚举支持多个处置动作；每条规则可配置多个动作。
- 并发与性能：
  - 分片锁字典 `ShardedLockDict` 与固定桶滑窗 `RollingWindowCounter`，降低锁竞争；`slots` 降低对象开销。
  - 只读目录（合约->产品/交易所映射）无锁查询。
- 动态配置：
  - 规则集合支持原子更新；报单限流窗口大小变化自动重建窗口。

## 快速开始
```bash
python -m unittest discover -s tests -p 'test_*.py' | cat
```

示例代码：
```python
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType

# 构造引擎
engine = RiskEngine(
    EngineConfig(
        contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
        contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
    ),
    rules=[
        AccountTradeMetricLimitRule(
            rule_id="VOL-1000", metric=MetricType.TRADE_VOLUME, threshold=1000,
            actions=(Action.SUSPEND_ACCOUNT_TRADING,), by_account=True, by_product=True,
        ),
        OrderRateLimitRule(
            rule_id="ORDER-50-1S", threshold=50, window_seconds=1,
            suspend_actions=(Action.SUSPEND_ORDERING,), resume_actions=(Action.RESUME_ORDERING,),
        ),
    ],
)

# 发送事件
engine.on_order(Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 10, 1_700_000_000_000_000_000))
engine.on_trade(Trade(1, 1, "ACC_001", "T2303", 100.0, 10, 1_700_000_000_000_000_100))
```

## 设计优势
- **高并发**：分片锁与桶化设计显著降低热点竞争，读路径无锁；规则快照读取避免全局锁。
- **低延迟**：核心路径仅包含少量哈希/数组操作，常数时间复杂度；对象使用 `slots` 降低属性查找成本。
- **可扩展**：
  - 新增指标：在 `MetricType` 中添加枚举，并在相应规则中支持即刻生效。
  - 新增维度：在 `InstrumentCatalog.resolve_dimensions` 中扩展映射，统计引擎无需修改。
  - 新增规则：继承 `Rule`，实现 `on_order/on_trade` 并注册到引擎。

## 局限与改进方向
- Python GIL 限制下，单进程对“百万级/秒、微秒级响应”的目标需要结合多进程/原生扩展（Cython/PyO3/Rust）或IO分离、核间分片。
- 如需更极致延迟与吞吐，建议：
  - 将 `ShardedLockDict`、`RollingWindowCounter` 下沉为 C 扩展（原子操作）。
  - 使用 DPDK/共享内存等零拷贝通道接入行情/订单流。
  - 采用 NUMA 亲和与 CPU 绑核，规避跨核迁移。

> 当前实现已在算法层面满足高并发与低延迟诉求，并提供清晰的扩展位；在生产中可按上述方向替换为原生实现以达成微秒级服务级别目标。
