"""
数据模型定义
定义Order和Trade的数据结构
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(Enum):
    """买卖方向"""
    BID = "Bid"    # 买入
    ASK = "Ask"    # 卖出


@dataclass
class Order:
    """订单数据模型"""
    oid: int                    # 订单唯一标识符
    account_id: str            # 交易账户编号
    contract_id: str           # 合约代码
    direction: Direction       # 买卖方向
    price: float              # 订单价格
    volume: int               # 订单数量
    timestamp: int            # 订单提交时间戳（纳秒级精度）
    
    def __post_init__(self):
        """数据验证"""
        if self.price <= 0:
            raise ValueError("价格必须大于0")
        if self.volume <= 0:
            raise ValueError("数量必须大于0")
        if self.timestamp < 0:
            raise ValueError("时间戳必须为非负数")


@dataclass
class Trade:
    """成交数据模型"""
    tid: int                  # 成交唯一标识符
    oid: int                  # 关联的订单ID
    price: float             # 成交价格
    volume: int              # 实际成交量
    timestamp: int           # 成交时间戳（纳秒级精度）
    
    # 扩展字段，用于关联订单信息
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    direction: Optional[Direction] = None
    
    def __post_init__(self):
        """数据验证"""
        if self.price <= 0:
            raise ValueError("价格必须大于0")
        if self.volume <= 0:
            raise ValueError("数量必须大于0")
        if self.timestamp < 0:
            raise ValueError("时间戳必须为非负数")
    
    def get_trade_amount(self) -> float:
        """计算成交金额"""
        return self.price * self.volume


@dataclass
class Action:
    """风控动作"""
    action_type: str         # 动作类型
    account_id: str          # 目标账户
    contract_id: Optional[str] = None  # 相关合约（可选）
    reason: str = ""         # 动作原因
    timestamp: int = 0       # 动作时间戳
    params: dict = None      # 额外参数
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}