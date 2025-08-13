from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .actions import Action
from .dimensions import InstrumentCatalog
from .metrics import MetricType
from .models import Order, Trade, Cancel
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


class RiskEngine:
    """实时风控引擎。

    设计目标：
    - 高并发：分片锁、无阻塞读、轻量对象。
    - 低延迟：常量时间路径、预分配窗口、简化对象分配。
    - 可扩展：规则与指标/维度可配置。
    """

    # ---------------------------- 新接口 ----------------------------
    def __init__(self, config: EngineConfig | RiskEngineConfig, rules: Optional[Sequence[Rule]] = None, action_sink: Optional[ActionSink] = None) -> None:
        # 兼容旧版 RiskEngineConfig
        if isinstance(config, RiskEngineConfig):
            engine_cfg = EngineConfig(
                contract_to_product=config.contract_to_product or {},
                contract_to_exchange={},
                deduplicate_actions=True,
            )
            rules = self._rules_from_legacy_config(config)
        else:
            engine_cfg = config
            rules = list(rules or [])
        self._config = engine_cfg
        self._rules: List[Rule] = list(rules)
        self._catalog = InstrumentCatalog(
            contract_to_product=engine_cfg.contract_to_product,
            contract_to_exchange=engine_cfg.contract_to_exchange,
        )
        self._daily_counter = MultiDimDailyCounter(ShardedLockDict())
        self._order_rate_windows: Dict[str, object] = {}
        self._lock = threading.RLock()  # 规则更新锁
        self._action_sink: ActionSink = action_sink or self._default_sink
        # 状态去重：避免频繁 RESUME/SUSPEND 抖动
        self._account_ordering_suspended: ShardedLockDict = ShardedLockDict()
        self._account_trading_suspended: ShardedLockDict = ShardedLockDict()
        # 订单索引（兼容旧接口，需要 trade->order 补全 account/contract）
        self._oid_to_order: Dict[int, Order] = {}
        # 兼容测试：暂存已发出的动作（仅最近一批）
        self._last_emitted: List[object] = []
        # 兼容旧版成交量日统计（仅用于测试断言）
        self._legacy_volume_state: Dict[Tuple[int, Tuple[str, ...]], float] = {}

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

    def _default_sink(self, action: Action, rule_id: str, obj: object) -> None:
        # 默认打印，可由调用方替换为消息总线/回调
        print(f"[Action] {action.name} by {rule_id} -> {obj}")

    def update_rules(self, new_rules: Sequence[Rule]) -> None:
        """原子替换规则集合（读路径无锁）。"""
        with self._lock:
            self._rules = list(new_rules)

    # ---------------------------- 事件入口（新） ----------------------------
    def on_order(self, order: Order) -> None:
        # 记录 order 以供 trade 关联
        self._oid_to_order[order.oid] = order
        ctx = RuleContext(
            catalog=self._catalog,
            daily_counter=self._daily_counter,
            order_rate_windows=self._order_rate_windows,  # 窗口计数器复用
            legacy_volume_state=self._legacy_volume_state,
        )
        # 先行：报单计数（可被某些规则使用）
        self._daily_counter.add(
            key=self._catalog.resolve_dimensions(order.account_id, order.contract_id, order.exchange_id, order.account_group_id),
            metric=MetricType.ORDER_COUNT,
            value=1.0,
            ns_ts=order.timestamp,
        )
        rules_snapshot = self._rules
        for rule in rules_snapshot:
            result = rule.on_order(ctx, order)
            if result and result.actions:
                self._emit_actions(rule.rule_id, result.actions, result.reasons, subject=order)

    def on_trade(self, trade: Trade) -> None:
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
        ctx = RuleContext(
            catalog=self._catalog,
            daily_counter=self._daily_counter,
            order_rate_windows=self._order_rate_windows,
            legacy_volume_state=self._legacy_volume_state,
        )
        rules_snapshot = self._rules
        for rule in rules_snapshot:
            result = rule.on_trade(ctx, trade)
            if result and result.actions:
                self._emit_actions(rule.rule_id, result.actions, result.reasons, subject=trade)

    def on_cancel(self, cancel: Cancel) -> None:
        """处理撤单事件，可触发相关风控规则（如撤单频率限制）。"""
        ctx = RuleContext(
            catalog=self._catalog,
            daily_counter=self._daily_counter,
            order_rate_windows=self._order_rate_windows,
            legacy_volume_state=self._legacy_volume_state,
        )
        rules_snapshot = self._rules
        for rule in rules_snapshot:
            result = rule.on_cancel(ctx, cancel)
            if result and result.actions:
                self._emit_actions(rule.rule_id, result.actions, result.reasons, subject=cancel)

    # ---------------------------- 事件入口（旧兼容） ----------------------------
    def ingest_order(self, order: Order) -> List[object]:
        """旧接口：返回动作列表的轻量对象，保留 .type.name 字段兼容测试。"""
        self._last_emitted = []
        self.on_order(order)
        return list(self._last_emitted)

    def ingest_trade(self, trade: Trade) -> List[object]:
        self._last_emitted = []
        self.on_trade(trade)
        return list(self._last_emitted)

    def ingest_cancel(self, cancel: Cancel) -> List[object]:
        """旧接口：处理撤单事件并返回动作列表。"""
        self._last_emitted = []
        self.on_cancel(cancel)
        return list(self._last_emitted)

    # ---------------------------- 动作处理 ----------------------------
    def _emit_actions(self, rule_id: str, actions: Sequence[Action], reasons: Sequence[str], subject: object) -> None:
        # 去抖逻辑：仅针对账户层面的 SUSPEND/RESUME 做状态机
        account_id = None
        if isinstance(subject, (Order, Trade, Cancel)):
            account_id = subject.account_id
        for action in actions:
            if self._config.deduplicate_actions and account_id:
                if action == Action.SUSPEND_ORDERING:
                    prev = self._account_ordering_suspended.incr(account_id, 0)
                    if prev == 0:
                        self._account_ordering_suspended.incr(account_id, 1)
                        self._action_sink(action, rule_id, subject)
                        self._collect_emitted(action, subject)
                    continue
                elif action == Action.RESUME_ORDERING:
                    prev = self._account_ordering_suspended.incr(account_id, 0)
                    if prev > 0:
                        self._account_ordering_suspended.incr(account_id, -prev)
                        self._action_sink(action, rule_id, subject)
                        self._collect_emitted(action, subject)
                    continue
                elif action == Action.SUSPEND_ACCOUNT_TRADING:
                    prev = self._account_trading_suspended.incr(account_id, 0)
                    if prev == 0:
                        self._account_trading_suspended.incr(account_id, 1)
                        self._action_sink(action, rule_id, subject)
                        self._collect_emitted(action, subject)
                    continue
                elif action == Action.RESUME_ACCOUNT_TRADING:
                    prev = self._account_trading_suspended.incr(account_id, 0)
                    if prev > 0:
                        self._account_trading_suspended.incr(account_id, -prev)
                        self._action_sink(action, rule_id, subject)
                        self._collect_emitted(action, subject)
                    continue
            # 默认直接下发
            self._action_sink(action, rule_id, subject)
            # 兼容：收集
            self._collect_emitted(action, subject)

    def _collect_emitted(self, action: Action, subject: object) -> None:
        from .actions import EmittedAction
        account_id = subject.account_id if isinstance(subject, (Order, Trade, Cancel)) else None
        self._last_emitted.append(EmittedAction(type=action, account_id=account_id))

    # ---------------------------- 热更新/快照（旧测试需要） ----------------------------
    def update_order_rate_limit(self, *, threshold: Optional[int] = None, window_ns: Optional[int] = None, dimension: Optional[StatsDimension] = None) -> None:
        new_rules: List[Rule] = []
        for r in self._rules:
            if isinstance(r, OrderRateLimitRule):
                th = r.threshold if threshold is None else threshold
                win_s = r.window_seconds if window_ns is None else max(1, window_ns // 1_000_000_000)
                dim = r.dimension
                if dimension is not None:
                    dim = dimension.value
                new_rules.append(
                    OrderRateLimitRule(
                        rule_id=r.rule_id,
                        threshold=th,
                        window_seconds=win_s,
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