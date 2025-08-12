from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Tuple

from .actions import Action, ActionEvent
from .models import Order, Trade


@dataclass(slots=True)
class RuleContext:
    # Mapping from contract_id to its product_id, e.g., {"T2303": "T10Y"}
    contract_to_product: Dict[str, str]


class BaseRule(ABC):
    @abstractmethod
    def on_order(self, order: Order, ctx: RuleContext) -> Iterable[ActionEvent]:
        ...

    @abstractmethod
    def on_trade(self, trade: Trade, ctx: RuleContext) -> Iterable[ActionEvent]:
        ...

    def on_tick(self, now_ns: int) -> Iterable[ActionEvent]:
        return ()


class SlidingCounter:
    """Lock-free sliding window counter aggregated in fixed buckets.

    Using a deque of (bucket_start_ns, count). Bucket size is configurable.
    Eviction runs amortized O(1) per add.
    """

    __slots__ = ("window_ns", "bucket_ns", "buckets", "total")

    def __init__(self, window_ns: int, bucket_ns: int = 1_000_000):
        if bucket_ns <= 0 or window_ns <= 0:
            raise ValueError("bucket_ns and window_ns must be positive")
        self.window_ns = window_ns
        self.bucket_ns = bucket_ns
        self.buckets: Deque[Tuple[int, int]] = deque()
        self.total = 0

    def _bucketize(self, ts_ns: int) -> int:
        return ts_ns - (ts_ns % self.bucket_ns)

    def _evict(self, now_ns: int) -> None:
        threshold = now_ns - self.window_ns
        while self.buckets and self.buckets[0][0] <= threshold:
            _, count = self.buckets.popleft()
            self.total -= count

    def add(self, ts_ns: int, n: int = 1) -> int:
        b = self._bucketize(ts_ns)
        if self.buckets and self.buckets[-1][0] == b:
            last_bucket, last_count = self.buckets[-1]
            self.buckets[-1] = (last_bucket, last_count + n)
        else:
            self.buckets.append((b, n))
        self.total += n
        self._evict(ts_ns)
        return self.total

    def current(self, now_ns: int) -> int:
        self._evict(now_ns)
        return self.total


class OrderRateLimitRule(BaseRule):
    """Rate limit number of order submissions per account in a time window.

    - threshold_per_account: default threshold
    - window_ns: sliding window size
    - dynamic_thresholds: optional account-specific overrides
    - pause_action: PAUSE_ORDER by default
    - resume_action: RESUME_ORDER by default
    """

    def __init__(
        self,
        *,
        threshold_per_account: int,
        window_ns: int,
        bucket_ns: int = 1_000_000,
        dynamic_thresholds: Optional[Dict[str, int]] = None,
        pause_action: Action = Action.PAUSE_ORDER,
        resume_action: Action = Action.RESUME_ORDER,
    ) -> None:
        self.threshold_default = threshold_per_account
        self.window_ns = window_ns
        self.bucket_ns = bucket_ns
        self.dynamic_thresholds = dynamic_thresholds or {}
        self.pause_action = pause_action
        self.resume_action = resume_action
        self.counters: Dict[str, SlidingCounter] = {}
        self.paused_accounts: Dict[str, bool] = defaultdict(bool)

    def _counter(self, account_id: str) -> SlidingCounter:
        c = self.counters.get(account_id)
        if c is None:
            c = SlidingCounter(self.window_ns, self.bucket_ns)
            self.counters[account_id] = c
        return c

    def _threshold(self, account_id: str) -> int:
        return self.dynamic_thresholds.get(account_id, self.threshold_default)

    def on_order(self, order: Order, ctx: RuleContext) -> Iterable[ActionEvent]:
        counter = self._counter(order.account_id)
        current = counter.add(order.timestamp, 1)
        threshold = self._threshold(order.account_id)
        is_paused = self.paused_accounts[order.account_id]
        if current > threshold and not is_paused:
            self.paused_accounts[order.account_id] = True
            yield ActionEvent(
                timestamp_ns=order.timestamp,
                account_id=order.account_id,
                action=self.pause_action,
                reason=f"order_rate>{threshold} in {self.window_ns}ns",
            )
        elif is_paused and current <= threshold:
            self.paused_accounts[order.account_id] = False
            yield ActionEvent(
                timestamp_ns=order.timestamp,
                account_id=order.account_id,
                action=self.resume_action,
                reason="order_rate back under threshold",
            )

    def on_trade(self, trade: Trade, ctx: RuleContext) -> Iterable[ActionEvent]:
        return ()

    def on_tick(self, now_ns: int) -> Iterable[ActionEvent]:
        # Periodic resume checks when there are no incoming orders
        for account_id, counter in self.counters.items():
            if self.paused_accounts.get(account_id) and counter.current(now_ns) <= self._threshold(account_id):
                self.paused_accounts[account_id] = False
                yield ActionEvent(
                    timestamp_ns=now_ns,
                    account_id=account_id,
                    action=self.resume_action,
                    reason="timed resume: order_rate back under threshold",
                )


class AccountVolumeLimitRule(BaseRule):
    """Daily trade volume cap per account with optional dimensions.

    dimensions: one or more of {"account", "contract", "product"}.
    If "product" is used, contract_to_product mapping from context is required.
    When cap is exceeded, PAUSE_TRADING is emitted for the specific dimension
    (e.g., one product) and remains until manually reset (not auto-resume).
    """

    def __init__(
        self,
        *,
        daily_cap: int,
        dimensions: Tuple[str, ...] = ("account",),
    ) -> None:
        self.daily_cap = daily_cap
        self.dimensions = dimensions
        self.volume_by_key: Dict[Tuple[str, ...], int] = defaultdict(int)
        self.paused_keys: Dict[Tuple[str, ...], bool] = defaultdict(bool)

    def _key(self, account_id: str, contract_id: Optional[str], ctx: RuleContext) -> Tuple[str, ...]:
        parts: List[str] = []
        for d in self.dimensions:
            if d == "account":
                parts.append(account_id)
            elif d == "contract":
                parts.append(contract_id or "*")
            elif d == "product":
                if not contract_id:
                    parts.append("*")
                else:
                    parts.append(ctx.contract_to_product.get(contract_id, "?"))
            else:
                parts.append("?")
        return tuple(parts)

    def on_order(self, order: Order, ctx: RuleContext) -> Iterable[ActionEvent]:
        return ()

    def on_trade(self, trade: Trade, ctx: RuleContext) -> Iterable[ActionEvent]:
        # We cannot access account_id from Trade directly; assume trade refers to order account elsewhere.
        # The engine will enrich with account_id when dispatching this rule.
        return ()  # Engine-driven update

    # Public API for engine to apply trade impact with enriched info
    def on_trade_with_account(
        self, *, account_id: str, contract_id: str, volume: int, timestamp_ns: int, ctx: RuleContext
    ) -> Iterable[ActionEvent]:
        key = self._key(account_id, contract_id, ctx)
        new_total = self.volume_by_key[key] + volume
        self.volume_by_key[key] = new_total
        if new_total > self.daily_cap and not self.paused_keys[key]:
            self.paused_keys[key] = True
            product_id = ctx.contract_to_product.get(contract_id)
            yield ActionEvent(
                timestamp_ns=timestamp_ns,
                account_id=account_id,
                action=Action.PAUSE_TRADING,
                reason=f"daily_volume>{self.daily_cap}",
                contract_id=contract_id,
                product_id=product_id,
            )

    def reset_daily(self) -> None:
        self.volume_by_key.clear()
        self.paused_keys.clear()