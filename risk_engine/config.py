from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence, Mapping


class Dimension(enum.IntEnum):
    ACCOUNT = 1
    CONTRACT = 2
    PRODUCT = 3
    ACCOUNT_CONTRACT = 4
    ACCOUNT_PRODUCT = 5


class VolumeMetric(enum.IntEnum):
    TRADE_VOLUME = 1
    TRADE_AMOUNT = 2


@dataclass(slots=True)
class VolumeLimitRuleConfig:
    metric: VolumeMetric = VolumeMetric.TRADE_VOLUME
    threshold: int = 1000
    dimension: Dimension = Dimension.ACCOUNT
    actions: Sequence[int] = (1,)  # default SUSPEND_ACCOUNT_TRADING


@dataclass(slots=True)
class OrderRateLimitRuleConfig:
    threshold_per_window: int = 50
    window_ns: int = 1_000_000_000  # 1s
    bucket_ns: int = 10_000_000  # 10ms
    auto_resume: bool = True
    actions_on_exceed: Sequence[int] = (2,)  # default SUSPEND_ACCOUNT_ORDERING
    actions_on_resume: Sequence[int] = (4,)  # RESUME_ACCOUNT_ORDERING


@dataclass(slots=True)
class EngineConfig:
    product_mapping: Mapping[str, str] = field(default_factory=dict)
    volume_limit: Optional[VolumeLimitRuleConfig] = field(default_factory=VolumeLimitRuleConfig)
    order_rate_limit: Optional[OrderRateLimitRuleConfig] = field(default_factory=OrderRateLimitRuleConfig)