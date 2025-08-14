from __future__ import annotations

from enum import Enum


class MetricType(str, Enum):
    """统计指标类型。支持扩展。"""

    TRADE_VOLUME = "trade_volume"  # 成交量（手）
    TRADE_NOTIONAL = "trade_notional"  # 成交金额（price * volume）
    ORDER_COUNT = "order_count"  # 报单量
    CANCEL_COUNT = "cancel_count"  # 撤单量（示例中未提供事件，可预留）
    
    # 扩展指标类型
    TRADE_COUNT = "trade_count"  # 成交笔数
    ORDER_REJECTION_RATE = "order_rejection_rate"  # 订单拒绝率
    PROFIT_LOSS = "profit_loss"  # 盈亏指标
    POSITION_SIZE = "position_size"  # 持仓规模
    MARGIN_UTILIZATION = "margin_utilization"  # 保证金使用率