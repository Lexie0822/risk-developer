from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Mapping

from .actions import Action
from .metrics import MetricType
from .dimensions import InstrumentCatalog, make_dimension_key
from .state import MultiDimDailyCounter, RollingWindowCounter
from .models import Order, Trade, Cancel
from .state import _ns_to_day_id


@dataclass(slots=True)
class RuleContext:
    """规则运行上下文：提供目录、统计状态等访问入口。"""

    catalog: InstrumentCatalog
    daily_counter: MultiDimDailyCounter
    order_rate_windows: Dict[str, RollingWindowCounter]  # rule_id -> counter
    # 兼容：旧版成交量规则的外部状态（按日、按维度累加）
    legacy_volume_state: Optional[Dict[Tuple[int, Tuple[str, ...]], float]] = None


@dataclass(slots=True)
class RuleResult:
    actions: List[Action]
    reasons: List[str]


class Rule:
    """规则基类。"""

    rule_id: str

    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        return None

    def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
        return None
    
    def on_cancel(self, ctx: RuleContext, cancel) -> Optional[RuleResult]:
        """处理撤单事件（可选实现）"""
        return None


@dataclass(slots=True)
class AccountTradeMetricLimitRule(Rule):
    """账户维度-按日指标阈值限制规则。

    - 支持多指标：成交量/成交金额/报单量/撤单量（报单量计数可在 on_order 中累加）。
    - 支持多维：账户、合约、产品、交易所、账户组任意组合。
    - 触发后可配置多个 Action。
    """

    rule_id: str
    metric: MetricType
    threshold: float
    actions: Tuple[Action, ...] = (Action.SUSPEND_ACCOUNT_TRADING,)
    # 统计维度开关：True 表示计入维度
    by_account: bool = True
    by_contract: bool = False
    by_product: bool = True
    by_exchange: bool = False
    by_account_group: bool = False

    def _make_key_for_order(self, ctx: RuleContext, order: Order):
        product_id = None
        if self.by_product:
            product_id = ctx.catalog.contract_to_product.get(order.contract_id)
        # 仅当 by_contract=True 才纳入 contract_id
        return make_dimension_key(
            account_id=order.account_id if self.by_account else None,
            contract_id=order.contract_id if self.by_contract else None,
            product_id=product_id,
            exchange_id=order.exchange_id if self.by_exchange else None,
            account_group_id=order.account_group_id if self.by_account_group else None,
        )

    def _make_key_for_trade(self, ctx: RuleContext, trade: Trade):
        product_id = None
        if self.by_product and trade.contract_id is not None:
            product_id = ctx.catalog.contract_to_product.get(trade.contract_id)
        return make_dimension_key(
            account_id=trade.account_id if self.by_account else None,
            contract_id=trade.contract_id if self.by_contract else None,
            product_id=product_id,
            exchange_id=trade.exchange_id if self.by_exchange else None,
            account_group_id=trade.account_group_id if self.by_account_group else None,
        )

    def _make_key_for_cancel(self, ctx: RuleContext, cancel: Cancel):
        product_id = None
        if self.by_product and cancel.contract_id is not None:
            product_id = ctx.catalog.contract_to_product.get(cancel.contract_id)
        return make_dimension_key(
            account_id=cancel.account_id if self.by_account else None,
            contract_id=cancel.contract_id if self.by_contract else None,
            product_id=product_id,
            exchange_id=cancel.exchange_id if self.by_exchange else None,
            account_group_id=cancel.account_group_id if self.by_account_group else None,
        )

    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        # 若监控报单量，则累加并判断
        if self.metric == MetricType.ORDER_COUNT:
            key = self._make_key_for_order(ctx, order)
            new_value = ctx.daily_counter.add(key, MetricType.ORDER_COUNT, 1.0, order.timestamp)
            if new_value >= self.threshold:
                return RuleResult(actions=list(self.actions), reasons=[
                    f"订单计数达到阈值: {new_value} >= {self.threshold}",
                ])
        return None

    def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
        # 计算指标增量
        if self.metric == MetricType.TRADE_VOLUME:
            value = float(trade.volume)
        elif self.metric == MetricType.TRADE_NOTIONAL:
            value = float(trade.volume) * float(trade.price)
        else:
            return None

        # 兼容路径：如果提供 legacy_volume_state，按其规则计数
        if ctx.legacy_volume_state is not None and self.rule_id == "LEGACY-VOLUME":
            # 使用维度开关构造 legacy key（不包含 contract，除非 by_contract=True）
            product_id = None
            if self.by_product and trade.contract_id is not None:
                product_id = ctx.catalog.contract_to_product.get(trade.contract_id)
            legacy_key = make_dimension_key(
                account_id=trade.account_id if self.by_account else None,
                contract_id=trade.contract_id if self.by_contract else None,
                product_id=product_id,
            )
            day_id = _ns_to_day_id(trade.timestamp)
            comp = (day_id, legacy_key)
            current = ctx.legacy_volume_state.get(comp, 0.0)
            new_value = current + value
            ctx.legacy_volume_state[comp] = new_value
        else:
            # 正常路径：多维日累加器
            key = self._make_key_for_trade(ctx, trade)
            new_value = ctx.daily_counter.add(key, self.metric, value, trade.timestamp)

        if new_value >= self.threshold:
            return RuleResult(actions=list(self.actions), reasons=[
                f"{self.metric} 达到阈值: {new_value} >= {self.threshold}",
            ])
        return None

    def on_cancel(self, ctx: RuleContext, cancel: Cancel) -> Optional[RuleResult]:
        # 若监控撤单量，则累加并判断
        if self.metric == MetricType.CANCEL_COUNT:
            key = self._make_key_for_cancel(ctx, cancel)
            new_value = ctx.daily_counter.add(key, MetricType.CANCEL_COUNT, float(cancel.volume), cancel.timestamp)
            if new_value >= self.threshold:
                return RuleResult(actions=list(self.actions), reasons=[
                    f"撤单量达到阈值: {new_value} >= {self.threshold}",
                ])
        return None


@dataclass(slots=True)
class OrderRateLimitRule(Rule):
    """报单频控规则（滑动窗口）。

    - 支持动态调整阈值与窗口大小。
    - 当窗口内计数超过阈值时触发暂停；当降至阈值以下时自动恢复。
    - 支持账户/合约/产品维度（通过 `dimension` 指定）。
    """

    rule_id: str
    threshold: int
    window_seconds: int
    suspend_actions: Tuple[Action, ...] = (Action.SUSPEND_ORDERING,)
    resume_actions: Tuple[Action, ...] = (Action.RESUME_ORDERING,)
    # 新增：支持维度（account/contract/product）。默认按账户维度
    dimension: str = "account"  # 可取值："account" | "contract" | "product"

    def _get_or_create_counter(self, ctx: RuleContext) -> RollingWindowCounter:
        counter = ctx.order_rate_windows.get(self.rule_id)
        if counter is None or counter._window_size != self.window_seconds:
            # 窗口调整时重建
            counter = RollingWindowCounter(self.window_seconds)
            ctx.order_rate_windows[self.rule_id] = counter
        return counter

    def _make_key(self, ctx: RuleContext, order: Order) -> Tuple[str, ...]:
        if self.dimension == "account":
            return (order.account_id,)
        if self.dimension == "contract":
            return (order.account_id, order.contract_id)
        if self.dimension == "product":
            product_id = ctx.catalog.contract_to_product.get(order.contract_id)
            return (order.account_id, product_id or order.contract_id)
        return (order.account_id,)

    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        counter = self._get_or_create_counter(ctx)
        key = self._make_key(ctx, order)
        counter.add(key, order.timestamp, 1)
        window_total = counter.total(key, order.timestamp)
        if window_total > self.threshold:
            return RuleResult(actions=list(self.suspend_actions), reasons=[
                f"报单频率超阈: {window_total} > {self.threshold} (窗口{self.window_seconds}s)",
            ])
        elif window_total <= self.threshold:
            return RuleResult(actions=list(self.resume_actions), reasons=[
                f"报单频率恢复: {window_total} <= {self.threshold} (窗口{self.window_seconds}s)",
            ])
        return None