from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Iterable

from .actions import Action
from .config import RiskEngineConfig
from .models import Order, Trade, ProductResolver
from .rules import BaseRule, VolumeLimitRule, OrderRateLimitRule, RuleContext
from .stats import StatsDimension


@dataclass(slots=True)
class RiskEngine:
    config: RiskEngineConfig
    product_resolver: ProductResolver = field(init=False)
    rules: List[BaseRule] = field(init=False, default_factory=list)
    _oid_to_order: Dict[int, Order] = field(init=False, default_factory=dict)
    # keep optional direct refs for management API
    _volume_rule: Optional[VolumeLimitRule] = field(init=False, default=None)
    _order_rate_rule: Optional[OrderRateLimitRule] = field(init=False, default=None)

    def __post_init__(self) -> None:
        self.product_resolver = ProductResolver(self.config.contract_to_product)
        self.rules = []
        context = RuleContext(product_resolver=self.product_resolver)
        if self.config.volume_limit is not None:
            vl = self.config.volume_limit
            self._volume_rule = VolumeLimitRule(
                threshold=vl.threshold,
                dimension=vl.dimension,
                context=context,
                reset_daily=vl.reset_daily,
            )
            self.rules.append(self._volume_rule)
        if self.config.order_rate_limit is not None:
            rl = self.config.order_rate_limit
            self._order_rate_rule = OrderRateLimitRule(
                threshold=rl.threshold,
                window_ns=rl.window_ns,
                dimension=rl.dimension,
                context=context,
            )
            self.rules.append(self._order_rate_rule)
        self._oid_to_order = {}

    def ingest_order(self, order: Order) -> List[Action]:
        # Keep minimal order book for correlating trades -> orders
        self._oid_to_order[order.oid] = order
        actions: List[Action] = []
        for rule in self.rules:
            actions.extend(rule.process_order(order))
        return actions

    def ingest_trade(self, trade: Trade) -> List[Action]:
        related_order: Optional[Order] = self._oid_to_order.get(trade.oid)
        actions: List[Action] = []
        for rule in self.rules:
            actions.extend(rule.process_trade(trade, related_order))
        return actions

    # Bulk/Vectorized ingestion for high-throughput pipelines
    def ingest_orders_bulk(self, orders: Iterable[Order]) -> List[Action]:
        actions: List[Action] = []
        append_order = self._oid_to_order.__setitem__
        rules = self.rules
        for order in orders:
            append_order(order.oid, order)
            for rule in rules:
                actions.extend(rule.process_order(order))
        return actions

    def ingest_trades_bulk(self, trades: Iterable[Trade]) -> List[Action]:
        actions: List[Action] = []
        oid_to_order = self._oid_to_order
        rules = self.rules
        for trade in trades:
            related_order: Optional[Order] = oid_to_order.get(trade.oid)
            for rule in rules:
                actions.extend(rule.process_trade(trade, related_order))
        return actions

    # Hot update APIs
    def update_volume_limit(self, *, threshold: Optional[int] = None, dimension: Optional[StatsDimension] = None, reset_daily: Optional[bool] = None) -> None:
        if self._volume_rule is not None:
            self._volume_rule.update_config(threshold=threshold, dimension=dimension, reset_daily=reset_daily)
            if threshold is not None:
                self.config.volume_limit.threshold = threshold
            if dimension is not None:
                self.config.volume_limit.dimension = dimension
            if reset_daily is not None:
                self.config.volume_limit.reset_daily = reset_daily

    def update_order_rate_limit(self, *, threshold: Optional[int] = None, window_ns: Optional[int] = None, dimension: Optional[StatsDimension] = None) -> None:
        if self._order_rate_rule is not None:
            self._order_rate_rule.update_config(threshold=threshold, window_ns=window_ns, dimension=dimension)
            if threshold is not None:
                self.config.order_rate_limit.threshold = threshold
            if window_ns is not None:
                self.config.order_rate_limit.window_ns = window_ns
            if dimension is not None:
                self.config.order_rate_limit.dimension = dimension

    # Simple persistence (snapshot/restore) focusing on volume rule state
    def snapshot(self) -> dict:
        data = {
            "config": {
                "contract_to_product": self.config.contract_to_product,
            }
        }
        if self._volume_rule is not None:
            data["volume_rule"] = self._volume_rule.snapshot_state()
        return data

    def restore(self, snapshot: dict) -> None:
        if not snapshot:
            return
        mapping = snapshot.get("config", {}).get("contract_to_product")
        if mapping:
            self.product_resolver.set_mapping(mapping)
            self.config.contract_to_product = dict(mapping)
        if self._volume_rule is not None and "volume_rule" in snapshot:
            self._volume_rule.restore_state(snapshot["volume_rule"])