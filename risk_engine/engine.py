from __future__ import annotations
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Order, Trade
from .actions import ActionEvent
from .config import EngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from .rules import VolumeLimitRule, OrderRateLimitRule


class RiskEngine:
    def __init__(self, cfg: EngineConfig) -> None:
        self.cfg = cfg
        # O(1) order lookup for trade attribution
        self._order_index: Dict[int, Tuple[str, str]] = {}

        def resolve_product(contract_id: str) -> str:
            return cfg.product_mapping.get(contract_id, contract_id[:1] if contract_id else "")

        def resolve_order_info(oid: int) -> Optional[Tuple[str, str]]:
            return self._order_index.get(oid)

        self.rules: List = []
        if cfg.volume_limit is not None:
            self.rules.append(VolumeLimitRule(cfg.volume_limit, resolve_product, resolve_order_info))
        if cfg.order_rate_limit is not None:
            self.rules.append(OrderRateLimitRule(cfg.order_rate_limit))

    # ingestion APIs
    def ingest_order(self, order: Order) -> Iterable[ActionEvent]:
        self._order_index[order.oid] = (order.account_id, order.contract_id)
        actions: List[ActionEvent] = []
        for rule in self.rules:
            actions.extend(rule.on_order(order))
        return actions

    def ingest_trade(self, trade: Trade) -> Iterable[ActionEvent]:
        actions: List[ActionEvent] = []
        for rule in self.rules:
            actions.extend(rule.on_trade(trade))
        return actions

    # dynamic controls
    def update_rate_limit(self, threshold: Optional[int] = None, window_ns: Optional[int] = None, bucket_ns: Optional[int] = None) -> None:
        for rule in self.rules:
            if isinstance(rule, OrderRateLimitRule):
                rule.update_threshold(threshold, window_ns, bucket_ns)