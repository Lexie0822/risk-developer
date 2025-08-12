from __future__ import annotations
from typing import Dict, Iterable, List, Optional, Tuple

from .models import Order, Trade
from .actions import ActionEvent, ActionType
from .config import (
    VolumeLimitRuleConfig,
    OrderRateLimitRuleConfig,
    Dimension,
    VolumeMetric,
)
from .window import RingBucketCounter


class BaseRule:
    def on_order(self, order: Order) -> Iterable[ActionEvent]:
        return ()

    def on_trade(self, trade: Trade) -> Iterable[ActionEvent]:
        return ()


class VolumeLimitRule(BaseRule):
    def __init__(self, cfg: VolumeLimitRuleConfig, resolve_product, resolve_order_info) -> None:
        self.cfg = cfg
        self.resolve_product = resolve_product
        self.resolve_order_info = resolve_order_info
        # key -> cumulative
        self.cum: Dict[str, float] = {}
        # track whether we already suspended to avoid duplicate actions
        self.suspended: Dict[str, bool] = {}

    def _key_for(self, account_id: str, contract_id: Optional[str]) -> str:
        dim = self.cfg.dimension
        if dim == Dimension.ACCOUNT:
            return account_id
        elif dim == Dimension.CONTRACT:
            return contract_id or ""
        elif dim == Dimension.PRODUCT:
            product_id = self.resolve_product(contract_id or "")
            return product_id
        elif dim == Dimension.ACCOUNT_CONTRACT:
            return f"{account_id}|{contract_id or ''}"
        elif dim == Dimension.ACCOUNT_PRODUCT:
            product_id = self.resolve_product(contract_id or "")
            return f"{account_id}|{product_id}"
        else:
            return account_id

    def on_trade(self, trade: Trade) -> Iterable[ActionEvent]:
        order_info = self.resolve_order_info(trade.oid)
        if order_info is None:
            return ()
        account_id, contract_id = order_info
        key = self._key_for(account_id, contract_id)
        if self.cfg.metric == VolumeMetric.TRADE_VOLUME:
            delta = trade.volume
        else:
            delta = trade.volume * trade.price
        new_total = self.cum.get(key, 0.0) + delta
        self.cum[key] = new_total
        if new_total >= self.cfg.threshold and not self.suspended.get(key, False):
            self.suspended[key] = True
            return [
                ActionEvent(
                    type=ActionType(action_id),
                    account_id=account_id,
                    timestamp=trade.timestamp,
                    reason=f"VolumeLimit exceeded: key={key} total={new_total} threshold={self.cfg.threshold}",
                    extra={"key": key},
                )
                for action_id in self.cfg.actions
            ]
        return ()


class OrderRateLimitRule(BaseRule):
    def __init__(self, cfg: OrderRateLimitRuleConfig) -> None:
        self.cfg = cfg
        self.counter = RingBucketCounter(cfg.window_ns, cfg.bucket_ns)
        # track suspended state per account
        self.suspended: Dict[str, bool] = {}

    def update_threshold(self, threshold: Optional[int] = None, window_ns: Optional[int] = None, bucket_ns: Optional[int] = None) -> None:
        if threshold is not None:
            self.cfg.threshold_per_window = threshold
        rebuild = False
        if window_ns is not None:
            self.cfg.window_ns = window_ns
            rebuild = True
        if bucket_ns is not None:
            self.cfg.bucket_ns = bucket_ns
            rebuild = True
        if rebuild:
            self.counter = RingBucketCounter(self.cfg.window_ns, self.cfg.bucket_ns)

    def on_order(self, order: Order) -> Iterable[ActionEvent]:
        account_id = order.account_id
        now_ns = order.timestamp
        self.counter.add(account_id, 1, now_ns)
        total = self.counter.sum(account_id, now_ns)
        if total > self.cfg.threshold_per_window and not self.suspended.get(account_id, False):
            self.suspended[account_id] = True
            return [
                ActionEvent(
                    type=ActionType(action_id),
                    account_id=account_id,
                    timestamp=now_ns,
                    reason=f"OrderRate exceeded: {total}>{self.cfg.threshold_per_window}",
                    extra={"rate": total},
                )
                for action_id in self.cfg.actions_on_exceed
            ]
        # handle resume
        if self.cfg.auto_resume and self.suspended.get(account_id, False):
            if total <= self.cfg.threshold_per_window:
                self.suspended[account_id] = False
                return [
                    ActionEvent(
                        type=ActionType(action_id),
                        account_id=account_id,
                        timestamp=now_ns,
                        reason=f"OrderRate resumed: {total}<={self.cfg.threshold_per_window}",
                        extra={"rate": total},
                    )
                    for action_id in self.cfg.actions_on_resume
                ]
        return ()