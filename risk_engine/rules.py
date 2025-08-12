from __future__ import annotations

from collections import deque, defaultdict
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from .actions import Action, ActionType
from .models import Order, Trade, ProductResolver
from .stats import MultiDimCounter, StatsDimension


Key = Tuple[str, ...]
NS_PER_DAY = 86_400_000_000_000


@dataclass(slots=True)
class RuleContext:
    product_resolver: ProductResolver


class BaseRule:
    def process_order(self, order: Order) -> List[Action]:
        return []

    def process_trade(self, trade: Trade, related_order: Optional[Order]) -> List[Action]:
        return []


class VolumeLimitRule(BaseRule):
    """Suspend trading for an account if traded volume exceeds threshold.

    Supports dimensions ACCOUNT, CONTRACT, PRODUCT. Counting happens on trades
    because they represent executed risk.
    """

    def __init__(
        self,
        threshold: int,
        dimension: StatsDimension,
        context: RuleContext,
        *,
        reset_daily: bool = True,
    ) -> None:
        self.threshold = threshold
        self.dimension = dimension
        self.context = context
        self.reset_daily = reset_daily
        self.counters = MultiDimCounter
        self.counters = MultiDimCounter()
        self.suspended_keys: set[Key] = set()
        self._last_reset_day: Optional[int] = None

    def _make_key(self, order: Optional[Order], trade: Trade) -> Key:
        # Try to use information from order if provided (for account_id, contract)
        if order is None:
            # Without order context, we cannot know account or contract safely.
            # In real systems, trade carries them; here we fallback to empty key.
            return ("unknown",)
        account_id = order.account_id
        if self.dimension == StatsDimension.ACCOUNT:
            return (account_id,)
        if self.dimension == StatsDimension.CONTRACT:
            return (account_id, order.contract_id)
        if self.dimension == StatsDimension.PRODUCT:
            product_id = self.context.product_resolver.resolve_product(order.contract_id) or "unknown"
            return (account_id, product_id)
        return (account_id,)

    def _maybe_daily_reset(self, now_ns: int) -> None:
        if not self.reset_daily:
            return
        current_day = now_ns // NS_PER_DAY
        if self._last_reset_day is None:
            self._last_reset_day = current_day
            return
        if current_day != self._last_reset_day:
            # New UTC day: reset counters and suspensions
            self.counters = MultiDimCounter()
            self.suspended_keys.clear()
            self._last_reset_day = current_day

    def process_trade(self, trade: Trade, related_order: Optional[Order]) -> List[Action]:
        actions: List[Action] = []
        self._maybe_daily_reset(trade.timestamp)
        key = self._make_key(related_order, trade)
        new_value = self.counters.add(key, trade.volume)
        if new_value > self.threshold and key not in self.suspended_keys:
            self.suspended_keys.add(key)
            account_id = related_order.account_id if related_order else "unknown"
            actions.append(
                Action(
                    type=ActionType.SUSPEND_ACCOUNT_TRADING,
                    account_id=account_id,
                    reason=f"Volume limit exceeded: {new_value} > {self.threshold} on {self.dimension.value}",
                    metadata={"key": key},
                )
            )
        return actions

    # Hot update and persistence helpers
    def update_config(
        self,
        *,
        threshold: Optional[int] = None,
        dimension: Optional[StatsDimension] = None,
        reset_daily: Optional[bool] = None,
    ) -> None:
        if threshold is not None:
            self.threshold = threshold
        if dimension is not None:
            self.dimension = dimension
        if reset_daily is not None:
            self.reset_daily = reset_daily

    def snapshot_state(self) -> dict:
        return {
            "threshold": self.threshold,
            "dimension": self.dimension.value,
            "reset_daily": self.reset_daily,
            "counters": list((list(k), v) for k, v in self.counters.items()),
            "suspended_keys": [list(k) for k in self.suspended_keys],
            "last_reset_day": self._last_reset_day,
        }

    def restore_state(self, state: dict) -> None:
        # Threshold/dimension/reset_daily are also restored for completeness
        if "threshold" in state:
            self.threshold = int(state["threshold"])
        if "dimension" in state:
            self.dimension = StatsDimension(state["dimension"])
        if "reset_daily" in state:
            self.reset_daily = bool(state["reset_daily"])
        # Rebuild counters and suspensions
        self.counters = MultiDimCounter()
        for k_list, v in state.get("counters", []):
            self.counters.add(tuple(k_list), int(v))
        self.suspended_keys = set(tuple(k) for k in state.get("suspended_keys", []))
        self._last_reset_day = state.get("last_reset_day")


class OrderRateLimitRule(BaseRule):
    """Suspend ordering if order submissions exceed threshold per time window.

    Uses a per-key sliding window with lock-free deques. Auto-resume when rate
    falls back below the configured threshold.
    """

    def __init__(
        self,
        threshold: int,
        window_ns: int,
        dimension: StatsDimension,
        context: RuleContext,
    ) -> None:
        self.threshold = threshold
        self.window_ns = window_ns
        self.dimension = dimension
        self.context = context
        self.events: Dict[Key, Deque[int]] = defaultdict(deque)
        self.suspended: Dict[Key, bool] = {}

    def _make_key(self, order: Order) -> Key:
        account_id = order.account_id
        if self.dimension == StatsDimension.ACCOUNT:
            return (account_id,)
        if self.dimension == StatsDimension.CONTRACT:
            return (account_id, order.contract_id)
        if self.dimension == StatsDimension.PRODUCT:
            product_id = self.context.product_resolver.resolve_product(order.contract_id) or "unknown"
            return (account_id, product_id)
        return (account_id,)

    def _evict_old(self, key: Key, now_ns: int) -> None:
        dq = self.events[key]
        boundary = now_ns - self.window_ns
        while dq and dq[0] <= boundary:
            dq.popleft()

    def process_order(self, order: Order) -> List[Action]:
        actions: List[Action] = []
        key = self._make_key(order)
        now_ns = order.timestamp
        dq = self.events[key]
        dq.append(now_ns)
        self._evict_old(key, now_ns)
        count = len(dq)

        is_suspended = self.suspended.get(key, False)
        if count > self.threshold and not is_suspended:
            self.suspended[key] = True
            actions.append(
                Action(
                    type=ActionType.SUSPEND_ORDERING,
                    account_id=order.account_id,
                    reason=f"Order rate {count}/{self.window_ns}ns exceeds {self.threshold}",
                    metadata={"key": key, "count": count},
                )
            )
        elif count <= self.threshold and is_suspended:
            self.suspended[key] = False
            actions.append(
                Action(
                    type=ActionType.RESUME_ORDERING,
                    account_id=order.account_id,
                    reason=f"Order rate normalized to {count}/{self.window_ns}ns",
                    metadata={"key": key, "count": count},
                )
            )
        return actions

    def update_config(
        self,
        *,
        threshold: Optional[int] = None,
        window_ns: Optional[int] = None,
        dimension: Optional[StatsDimension] = None,
    ) -> None:
        if threshold is not None:
            self.threshold = threshold
        if window_ns is not None:
            self.window_ns = window_ns
        if dimension is not None:
            self.dimension = dimension