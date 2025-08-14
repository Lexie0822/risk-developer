from __future__ import annotations

from enum import Enum, auto


class MetricType(Enum):
    """指标类型枚举。
    
    支持扩展点需求：成交量、成交金额、报单量、撤单量等多种指标。
    """

    # 成交相关指标
    TRADE_VOLUME = auto()     # 成交量（手数）
    TRADE_NOTIONAL = auto()   # 成交金额（价格×数量）
    TRADE_COUNT = auto()      # 成交笔数
    
    # 订单相关指标  
    ORDER_COUNT = auto()      # 报单量（笔数）
    ORDER_VOLUME = auto()     # 报单总量（手数）
    ORDER_NOTIONAL = auto()   # 报单总金额
    
    # 撤单相关指标（扩展点）
    CANCEL_COUNT = auto()     # 撤单量（笔数）
    CANCEL_VOLUME = auto()    # 撤单总量（手数）
    CANCEL_RATE = auto()      # 撤单率（撤单量/报单量）
    
    # 持仓相关指标
    POSITION_VOLUME = auto()  # 持仓量
    POSITION_NOTIONAL = auto() # 持仓金额
    
    # 风险相关指标
    PNL_REALIZED = auto()     # 已实现盈亏
    PNL_UNREALIZED = auto()   # 未实现盈亏
    MARGIN_USED = auto()      # 已用保证金