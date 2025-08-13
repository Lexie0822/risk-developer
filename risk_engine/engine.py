from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple
import time

from .actions import Action
from .dimensions import InstrumentCatalog
from .metrics import MetricType
from .models import Order, Trade
from .rules import (
    Rule,
    RuleContext,
    RuleResult,
    AccountTradeMetricLimitRule,
    OrderRateLimitRule,
)
from .state import MultiDimDailyCounter, ShardedLockDict
from .config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from .stats import StatsDimension


ActionSink = Callable[[Action, str, object], None]


@dataclass(slots=True)
class EngineConfig:
    """引擎配置。

    - 目录初始化：合约->产品、合约->交易所 映射
    - 去抖：防止重复发送 RESUME/SUSPEND
    """

    contract_to_product: Dict[str, str] = field(default_factory=dict)
    contract_to_exchange: Dict[str, str] = field(default_factory=dict)
    deduplicate_actions: bool = True
    # 性能优化选项
    enable_fast_path: bool = True  # 启用快速路径优化
    batch_size: int = 1000  # 批处理大小
    thread_local_cache: bool = True  # 启用线程本地缓存


# 线程本地存储的预分配缓存
_thread_local = threading.local()

def _get_thread_cache():
    """获取线程本地缓存"""
    if not hasattr(_thread_local, 'rule_context'):
        _thread_local.rule_context = None
        _thread_local.dimension_cache = {}
        _thread_local.result_buffer = []
    return _thread_local


class RiskEngine:
    """实时风控引擎。

    设计目标：
    - 高并发：分片锁、无阻塞读、轻量对象。
    - 低延迟：常量时间路径、预分配窗口、简化对象分配。
    - 可扩展：规则与指标/维度可配置。
    
    性能优化：
    - 快速路径：简单场景避免复杂计算
    - 内存池：减少对象分配
    - 线程本地缓存：减少重复计算
    """

    # ---------------------------- 新接口 ----------------------------
    def __init__(self, config: EngineConfig | RiskEngineConfig, rules: Optional[Sequence[Rule]] = None, action_sink: Optional[ActionSink] = None) -> None:
        # 兼容旧版 RiskEngineConfig
        if isinstance(config, RiskEngineConfig):
            compat_config = EngineConfig(
                contract_to_product=config.contract_to_product,
                contract_to_exchange={},
                deduplicate_actions=True,
            )
            self._config = compat_config
            # 从旧配置创建规则
            rules = self._rules_from_legacy_config(config)
        else:
            self._config = config
            rules = list(rules) if rules else []

        self._catalog = InstrumentCatalog(
            contract_to_product=self._config.contract_to_product,
            contract_to_exchange=self._config.contract_to_exchange,
        )
        self._daily_counter = MultiDimDailyCounter(ShardedLockDict())
        self._order_rate_windows: Dict[str, object] = {}  # rule_id -> RollingWindowCounter

        # 动态规则管理
        self._rules: List[Rule] = rules
        self._rules_lock = threading.RLock()

        # 去抖：防止重复动作
        self._last_action_state: Dict[str, Tuple[Action, int]] = {}  # 账户 -> (action, timestamp_ns)
        self._action_sink = action_sink

        # 兼容：Order ID -> Order 映射，用于 Trade 补全字段
        self._oid_to_order: Dict[int, Order] = {}

        # 性能优化：预分配缓存
        self._rule_context_cache: Optional[RuleContext] = None
        self._stats = {
            'events_processed': 0,
            'rules_evaluated': 0,
            'actions_emitted': 0,
            'avg_latency_ns': 0,
            'peak_latency_ns': 0,
        }
        
        # 快速路径优化
        self._fast_path_enabled = self._config.enable_fast_path
        self._simple_rules_cache = {}  # 缓存简单规则的结果

        # 兼容旧版本的变量
        self._legacy_volume_state: Dict[Tuple[int, Tuple[Tuple[str, str], ...]], float] = {}
        self._last_emitted: List[object] = []

    def _rules_from_legacy_config(self, legacy: RiskEngineConfig) -> List[Rule]:
        rules: List[Rule] = []
        if legacy.volume_limit is not None:
            vl = legacy.volume_limit
            by_account = True
            by_contract = vl.dimension == StatsDimension.CONTRACT
            by_product = vl.dimension == StatsDimension.PRODUCT or not by_contract
            # metric 仅支持 trade_volume
            rules.append(
                AccountTradeMetricLimitRule(
                    rule_id="LEGACY-VOLUME",
                    metric=MetricType.TRADE_VOLUME,
                    threshold=float(vl.threshold),
                    actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                    by_account=by_account,
                    by_contract=by_contract,
                    by_product=by_product,
                    by_exchange=False,
                    by_account_group=False,
                )
            )
        if legacy.order_rate_limit is not None:
            rl = legacy.order_rate_limit
            # 维度：ACCOUNT/CONTRACT/PRODUCT -> 设置在规则上
            dim = rl.dimension.value
            window_seconds = max(1, rl.window_ns // 1_000_000_000)
            rules.append(
                OrderRateLimitRule(
                    rule_id="LEGACY-ORDER-RATE",
                    threshold=rl.threshold,
                    window_seconds=window_seconds,
                    suspend_actions=(Action.SUSPEND_ORDERING,),
                    resume_actions=(Action.RESUME_ORDERING,),
                    dimension=dim,
                )
            )
        return rules

    def _get_cached_rule_context(self) -> RuleContext:
        """获取缓存的规则上下文，减少对象分配"""
        if self._config.thread_local_cache:
            cache = _get_thread_cache()
            if cache.rule_context is None:
                cache.rule_context = RuleContext(
                    catalog=self._catalog,
                    daily_counter=self._daily_counter,
                    order_rate_windows=self._order_rate_windows,
                    legacy_volume_state=self._legacy_volume_state,
                )
            return cache.rule_context
        
        if self._rule_context_cache is None:
            self._rule_context_cache = RuleContext(
                catalog=self._catalog,
                daily_counter=self._daily_counter,
                order_rate_windows=self._order_rate_windows,
                legacy_volume_state=self._legacy_volume_state,
            )
        return self._rule_context_cache

    def _should_process_fast_path(self, account_id: str, contract_id: str) -> bool:
        """检查是否可以使用快速路径"""
        if not self._fast_path_enabled:
            return False
        
        # 对于高频账户/合约，使用快速路径
        cache_key = f"{account_id}:{contract_id}"
        return cache_key in self._simple_rules_cache

    def on_order(self, order: Order) -> None:
        start_time = time.perf_counter_ns()
        
        # 记录 order 以供 trade 关联
        self._oid_to_order[order.oid] = order
        
        # 快速路径检查
        if self._should_process_fast_path(order.account_id, order.contract_id):
            self._stats['events_processed'] += 1
            return
        
        ctx = self._get_cached_rule_context()
        
        # 先行：报单计数（可被某些规则使用）
        if self._config.thread_local_cache:
            cache = _get_thread_cache()
            dim_key = cache.dimension_cache.get(f"{order.account_id}:{order.contract_id}")
            if dim_key is None:
                dim_key = self._catalog.resolve_dimensions(
                    order.account_id, order.contract_id, 
                    order.exchange_id, order.account_group_id
                )
                cache.dimension_cache[f"{order.account_id}:{order.contract_id}"] = dim_key
        else:
            dim_key = self._catalog.resolve_dimensions(
                order.account_id, order.contract_id, 
                order.exchange_id, order.account_group_id
            )
        
        self._daily_counter.add(
            key=dim_key,
            metric=MetricType.ORDER_COUNT,
            value=1.0,
            ns_ts=order.timestamp,
        )
        
        # 批量处理规则
        rules_snapshot = self._rules
        for rule in rules_snapshot:
            result = rule.on_order(ctx, order)
            if result and result.actions:
                self._emit_actions(rule.rule_id, result.actions, result.reasons, subject=order)
                self._stats['rules_evaluated'] += 1

        # 更新性能统计
        latency = time.perf_counter_ns() - start_time
        self._stats['events_processed'] += 1
        self._stats['avg_latency_ns'] = (self._stats['avg_latency_ns'] * 0.95 + latency * 0.05)
        self._stats['peak_latency_ns'] = max(self._stats['peak_latency_ns'], latency)

    def on_trade(self, trade: Trade) -> None:
        start_time = time.perf_counter_ns()
        
        # 尝试从订单补全缺失字段
        if (trade.account_id is None or trade.contract_id is None) and trade.oid in self._oid_to_order:
            o = self._oid_to_order[trade.oid]
            if trade.account_id is None:
                trade.account_id = o.account_id
            if trade.contract_id is None:
                trade.contract_id = o.contract_id
            if trade.exchange_id is None:
                trade.exchange_id = o.exchange_id
            if trade.account_group_id is None:
                trade.account_group_id = o.account_group_id
        
        # 快速路径检查
        if self._should_process_fast_path(trade.account_id or "", trade.contract_id or ""):
            self._stats['events_processed'] += 1
            return
            
        ctx = self._get_cached_rule_context()
        rules_snapshot = self._rules
        for rule in rules_snapshot:
            result = rule.on_trade(ctx, trade)
            if result and result.actions:
                self._emit_actions(rule.rule_id, result.actions, result.reasons, subject=trade)
                self._stats['rules_evaluated'] += 1

        # 更新性能统计
        latency = time.perf_counter_ns() - start_time
        self._stats['events_processed'] += 1
        self._stats['avg_latency_ns'] = (self._stats['avg_latency_ns'] * 0.95 + latency * 0.05)
        self._stats['peak_latency_ns'] = max(self._stats['peak_latency_ns'], latency)

    def get_performance_stats(self) -> dict:
        """获取性能统计信息"""
        return {
            'events_per_second': self._stats['events_processed'] / max(1, time.time()),
            'avg_latency_us': self._stats['avg_latency_ns'] / 1000,
            'peak_latency_us': self._stats['peak_latency_ns'] / 1000,
            'rules_evaluated': self._stats['rules_evaluated'],
            'actions_emitted': self._stats['actions_emitted'],
        }

    def _emit_actions(self, rule_id: str, actions: List[Action], reasons: List[str], subject: object) -> None:
        """发出风控动作"""
        for i, action in enumerate(actions):
            reason = reasons[i] if i < len(reasons) else "规则触发"
            
            # 去抖逻辑：避免重复动作
            if self._config.deduplicate_actions and hasattr(subject, 'account_id'):
                account_id = getattr(subject, 'account_id', '')
                current_time = time.time_ns()
                last_state = self._last_action_state.get(account_id)
                
                if last_state and last_state[0] == action:
                    # 避免在短时间内重复相同动作
                    if current_time - last_state[1] < 1_000_000_000:  # 1秒内
                        continue
                
                self._last_action_state[account_id] = (action, current_time)
            
            # 兼容测试：构造轻量动作对象
            from .actions import EmittedAction
            emitted = EmittedAction(type=action, account_id=getattr(subject, 'account_id', None), reason=reason)
            self._last_emitted.append(emitted)
            
            # 调用外部处理器
            if self._action_sink:
                self._action_sink(action, rule_id, subject)
            else:
                print(f"[Action] {action.name} by {rule_id} -> {subject}")
            
            self._stats['actions_emitted'] += 1

    def update_rules(self, new_rules: Sequence[Rule]) -> None:
        """原子替换规则集合（读路径无锁）。"""
        with self._rules_lock:
            self._rules = list(new_rules)

    # ---------------------------- 兼容性接口 ----------------------------
    def ingest_order(self, order: Order) -> List[object]:
        """旧接口：返回动作列表的轻量对象，保留 .type.name 字段兼容测试。"""
        self._last_emitted = []
        self.on_order(order)
        return list(self._last_emitted)

    def ingest_trade(self, trade: Trade) -> List[object]:
        """旧接口：返回动作列表的轻量对象，保留 .type.name 字段兼容测试。"""
        self._last_emitted = []
        self.on_trade(trade)
        return list(self._last_emitted)

    # ---------------------------- 动态配置更新 ----------------------------
    def update_order_rate_limit(self, *, threshold: Optional[int] = None, window_seconds: Optional[int] = None, dimension: Optional[str] = None) -> None:
        """动态更新报单频控规则"""
        new_rules: List[Rule] = []
        for r in self._rules:
            if isinstance(r, OrderRateLimitRule):
                th = r.threshold if threshold is None else threshold
                ws = r.window_seconds if window_seconds is None else window_seconds
                dim = r.dimension if dimension is None else dimension
                new_rules.append(
                    OrderRateLimitRule(
                        rule_id=r.rule_id,
                        threshold=th,
                        window_seconds=ws,
                        suspend_actions=r.suspend_actions,
                        resume_actions=r.resume_actions,
                        dimension=dim,
                    )
                )
            else:
                new_rules.append(r)
        self.update_rules(new_rules)

    def update_volume_limit(self, *, threshold: Optional[int] = None, dimension: Optional[StatsDimension] = None, reset_daily: Optional[bool] = None) -> None:
        new_rules: List[Rule] = []
        for r in self._rules:
            if isinstance(r, AccountTradeMetricLimitRule):
                th = r.threshold if threshold is None else float(threshold)
                by_contract = r.by_contract
                by_product = r.by_product
                if dimension is not None:
                    by_contract = dimension == StatsDimension.CONTRACT
                    by_product = dimension == StatsDimension.PRODUCT or not by_contract
                new_rules.append(
                    AccountTradeMetricLimitRule(
                        rule_id=r.rule_id,
                        metric=r.metric,
                        threshold=th,
                        actions=r.actions,
                        by_account=True,
                        by_contract=by_contract,
                        by_product=by_product,
                        by_exchange=r.by_exchange,
                        by_account_group=r.by_account_group,
                    )
                )
            else:
                new_rules.append(r)
        self.update_rules(new_rules)

    def snapshot(self) -> dict:
        # 简化的快照，仅包含配置与按日成交量状态
        legacy_list = []
        for (day_id, dim_key), v in self._legacy_volume_state.items():
            # dim_key: Tuple[Tuple[str,str], ...]
            legacy_list.append({
                "day_id": day_id,
                "dim_key": list(dim_key),
                "value": v,
            })
        return {
            "config": {
                "contract_to_product": dict(self._config.contract_to_product),
            },
            "legacy_volume_state": legacy_list,
        }

    def restore(self, snapshot: dict) -> None:
        if not snapshot:
            return
        mapping = snapshot.get("config", {}).get("contract_to_product")
        if mapping:
            self._config.contract_to_product = dict(mapping)
            # 重建目录
            self._catalog = InstrumentCatalog(
                contract_to_product=self._config.contract_to_product,
                contract_to_exchange=self._config.contract_to_exchange,
            )
        legacy_state = snapshot.get("legacy_volume_state")
        if isinstance(legacy_state, list):
            restored: Dict[Tuple[int, Tuple[Tuple[str, str], ...]], float] = {}
            for item in legacy_state:
                day_id = int(item["day_id"])  # type: ignore[index]
                dim_key_list = item["dim_key"]  # type: ignore[index]
                # convert list of [k,v] to tuple of tuples
                dim_key = tuple((str(k), str(v)) for k, v in dim_key_list)
                val = float(item["value"])  # type: ignore[index]
                restored[(day_id, dim_key)] = val
            self._legacy_volume_state = restored


# 便捷构造函数

def default_engine() -> RiskEngine:
    rules: List[Rule] = [
        # 示例规则：账户日成交量达到 1000 手暂停交易
        AccountTradeMetricLimitRule(
            rule_id="R-ACC-DAY-VOL",
            metric=MetricType.TRADE_VOLUME,
            threshold=1000,
            actions=(Action.SUSPEND_ACCOUNT_TRADING,),
            by_account=True,
            by_product=True,  # 产品维度汇总（合约归并）
        ),
        # 示例规则：账户报单频率 1 秒内超过 50 次，暂停报单；回落后恢复
        OrderRateLimitRule(
            rule_id="R-ACC-ORDER-RATE",
            threshold=50,
            window_seconds=1,
            suspend_actions=(Action.SUSPEND_ORDERING,),
            resume_actions=(Action.RESUME_ORDERING,),
        ),
    ]
    cfg = EngineConfig(
        contract_to_product={},
        contract_to_exchange={},
        deduplicate_actions=True,
    )
    return RiskEngine(cfg, rules)