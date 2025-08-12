from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

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

    def __post_init__(self) -> None:
        self.product_resolver = ProductResolver(self.config.contract_to_product)
        self.rules = []
        context = RuleContext(product_resolver=self.product_resolver)
        if self.config.volume_limit is not None:
            vl = self.config.volume_limit
            self.rules.append(
                VolumeLimitRule(
                    threshold=vl.threshold,
                    dimension=vl.dimension,
                    context=context,
                )
            )
        if self.config.order_rate_limit is not None:
            rl = self.config.order_rate_limit
            self.rules.append(
                OrderRateLimitRule(
                    threshold=rl.threshold,
                    window_ns=rl.window_ns,
                    dimension=rl.dimension,
                    context=context,
                )
            )
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