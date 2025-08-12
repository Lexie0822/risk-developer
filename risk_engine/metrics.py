from __future__ import annotations

from enum import Enum


class MetricType(str, Enum):
    """统计指标类型。支持扩展。"""

    TRADE_VOLUME = "trade_volume"  # 成交量（手）
    TRADE_NOTIONAL = "trade_notional"  # 成交金额（price * volume）
    ORDER_COUNT = "order_count"  # 报单量
    CANCEL_COUNT = "cancel_count"  # 撤单量（示例中未提供事件，可预留）