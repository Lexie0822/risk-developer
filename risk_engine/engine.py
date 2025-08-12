from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from .actions import ActionEvent
from .models import Order, Trade
from .rules import AccountVolumeLimitRule, BaseRule, RuleContext


class RiskEngine:
    def __init__(
        self,
        *,
        rules: List[BaseRule],
        contract_to_product: Optional[Dict[str, str]] = None,
    ) -> None:
        self.rules = rules
        self.contract_to_product = contract_to_product or {}
        # Lightweight cache from oid to (account_id, contract_id)
        self._order_index: Dict[int, tuple[str, str]] = {}
        # Account status flags that downstream systems may consult
        self.account_paused_for_order: Dict[str, bool] = defaultdict(bool)
        self.account_paused_for_trading: Dict[str, bool] = defaultdict(bool)

    def _ctx(self) -> RuleContext:
        return RuleContext(contract_to_product=self.contract_to_product)

    def process_order(self, order: Order) -> List[ActionEvent]:
        self._order_index[order.oid] = (order.account_id, order.contract_id)
        ctx = self._ctx()
        actions: List[ActionEvent] = []
        for rule in self.rules:
            actions.extend(rule.on_order(order, ctx))
        self._apply_side_effects(actions)
        return actions

    def process_trade(self, trade: Trade) -> List[ActionEvent]:
        # Enrich with original order metadata if available
        account_id: Optional[str] = None
        contract_id: Optional[str] = None
        if trade.oid in self._order_index:
            account_id, contract_id = self._order_index[trade.oid]
        ctx = self._ctx()
        actions: List[ActionEvent] = []
        for rule in self.rules:
            if isinstance(rule, AccountVolumeLimitRule) and account_id and contract_id:
                actions.extend(
                    rule.on_trade_with_account(
                        account_id=account_id,
                        contract_id=contract_id,
                        volume=trade.volume,
                        timestamp_ns=trade.timestamp,
                        ctx=ctx,
                    )
                )
            else:
                actions.extend(rule.on_trade(trade, ctx))
        self._apply_side_effects(actions)
        return actions

    def tick(self, now_ns: Optional[int] = None) -> List[ActionEvent]:
        now_ns = now_ns or time.time_ns()
        actions: List[ActionEvent] = []
        for rule in self.rules:
            actions.extend(rule.on_tick(now_ns))
        self._apply_side_effects(actions)
        return actions

    def _apply_side_effects(self, actions: Iterable[ActionEvent]) -> None:
        for a in actions:
            if a.action.name.startswith("PAUSE_ORDER"):
                self.account_paused_for_order[a.account_id] = True
            elif a.action.name.startswith("RESUME_ORDER"):
                self.account_paused_for_order[a.account_id] = False
            elif a.action.name.startswith("PAUSE_TRADING"):
                self.account_paused_for_trading[a.account_id] = True
            elif a.action.name.startswith("RESUME_TRADING"):
                self.account_paused_for_trading[a.account_id] = False