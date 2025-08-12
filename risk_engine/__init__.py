"""实时风控引擎包

该包提供高并发、低延迟的风控规则引擎实现，支持多维统计与动态规则调整。
"""

from .models import Order, Trade, Direction
from .actions import Action
from .metrics import MetricType
from .engine import RiskEngine, EngineConfig
from .rules import (
    Rule,
    AccountTradeMetricLimitRule,
    OrderRateLimitRule,
)

# 兼容旧版导出
from .config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig
from .stats import StatsDimension