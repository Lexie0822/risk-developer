from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from .stats import StatsDimension


@dataclass(slots=True)
class VolumeLimitRuleConfig:
    threshold: int = 1000  # e.g. 1000 lots per day
    dimension: StatsDimension = StatsDimension.ACCOUNT
    metric: str = "trade_volume"  # kept for extensibility
    reset_daily: bool = True  # if True, reset counters at UTC day boundaries


@dataclass(slots=True)
class OrderRateLimitRuleConfig:
    threshold: int = 50  # e.g. 50 orders per window
    window_ns: int = 1_000_000_000  # 1 second by default
    dimension: StatsDimension = StatsDimension.ACCOUNT


@dataclass(slots=True)
class RiskEngineConfig:
    volume_limit: Optional[VolumeLimitRuleConfig] = field(
        default_factory=VolumeLimitRuleConfig
    )
    order_rate_limit: Optional[OrderRateLimitRuleConfig] = field(
        default_factory=OrderRateLimitRuleConfig
    )
    # contract_id -> product_id mapping for product dimension support
    contract_to_product: Dict[str, str] = field(default_factory=dict)