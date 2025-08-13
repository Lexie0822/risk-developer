# 实时风控引擎（Python）

本项目实现一套面向期货/衍生品交易场景的实时风控引擎，支持高并发事件处理、低延迟判断、多维指标统计与动态规则配置。

## 功能特性
- 多规则：
  - 单账户日成交量/成交金额/报单量/撤单量限制（可配置维度：账户/合约/产品/交易所/账户组任意组合）。
  - 报单频率控制：支持 1 s / 60 s 等可调滑窗，超阈自动暂停，计数回落后自动恢复；阈值与窗口均可在运行时热更新。
- 多维统计：
  - 多维日累加器 `MultiDimDailyCounter`，支持产品维度（合约归并）与拓展维度。
- 动作系统：
  - `Action` 枚举支持多个处置动作；每条规则可配置多个动作。
- 并发与性能：
  - 分片锁字典 `ShardedLockDict` 与固定桶滑窗 `RollingWindowCounter`，降低锁竞争；`slots` 降低对象开销。
  - 只读目录（合约->产品/交易所映射）无锁查询。
- 动态配置：
  - 规则集合支持原子更新；报单限流窗口大小变化自动重建窗口。

## 安装与运行
```bash
# 安装依赖
python -m pip install -r requirements.txt

# 运行全部单元测试
python -m unittest discover -s tests -p 'test_*.py' | cat

# 运行吞吐基准（可选）
python /workspace/bench.py
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


## 兼容老接口（RiskEngineConfig）
```python
from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.stats import StatsDimension

engine = RiskEngine(
    RiskEngineConfig(
        volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=StatsDimension.ACCOUNT, reset_daily=True),
        order_rate_limit=OrderRateLimitRuleConfig(threshold=50, window_ns=1_000_000_000, dimension=StatsDimension.PRODUCT),
        contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
    )
)

# 老接口事件入口（返回兼容测试的动作列表）
acts1 = engine.ingest_order(Order(oid=1, account_id="ACC", contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=1_700_000_000_000_000_000))
acts2 = engine.ingest_trade(Trade(tid=1, oid=1, price=100.0, volume=10, timestamp=1_700_000_000_000_000_100))
```

## 热更新与快照
```python
# 热更新（阈值、窗口、维度）
engine.update_order_rate_limit(threshold=100, window_ns=500_000_000)
engine.update_volume_limit(threshold=10_000, dimension=StatsDimension.PRODUCT)

# 快照/恢复（包含合约-产品映射与按日成交量状态）
snap = engine.snapshot()
engine.restore(snap)
```

## 目录结构
- `risk_engine/models.py`：订单、成交、方向与扩展维度
- `risk_engine/actions.py`：动作枚举与兼容测试的 `EmittedAction`
- `risk_engine/metrics.py`：指标类型定义
- `risk_engine/dimensions.py`：合约静态属性目录与维度键
- `risk_engine/state.py`：分片字典、日计数、多桶滑窗
- `risk_engine/rules.py`：规则实现（成交/金额/报单量限制、报单频控）
- `risk_engine/engine.py`：引擎装配、事件入口、动作去抖、热更新与快照
- `risk_engine/config.py`、`risk_engine/stats.py`：老接口兼容
- `tests/`：单元测试
- `bench.py`：吞吐评估脚本（本机环境下运行）

## 基准与性能说明
- 运行：`python3 /workspace/bench.py`
- 说明：该脚本用于评估当前机器上的单进程吞吐。生产中建议多进程分片（按账户/Key）、绑核与原生扩展（Cython/Rust）以达成“百万级/秒、微秒级”目标，架构与实现已为零拷贝/原生加速留好接口。

## 需求符合性清单
- [x] 规则1：单账户成交量限制（支持指标扩展：金额 / 报单量 / 撤单量；支持账户 / 合约 / 产品 / 交易所 / 账户组等任意维度组合）
- [x] 规则2：报单频率控制（支持动态阈值与窗口、自动恢复；支持账户/合约/产品维度）
- [x] Action：统一枚举输出，规则可配置多个动作
- [x] 多维统计引擎：支持产品维度聚合，可扩展新增维度
- [x] 高并发/低延迟：分片锁+桶化滑窗+slots 优化；读路径无锁
- [x] 接口与文档：新/旧接口、热更新、快照、示例、测试与基准脚本
