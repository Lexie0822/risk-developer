"""
金融风控系统数据模型定义
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class Direction(Enum):
    """买卖方向枚举"""
    BID = "Bid"
    ASK = "Ask"


class ActionType(Enum):
    """风控动作类型枚举"""
    SUSPEND_ACCOUNT = "suspend_account"  # 暂停账户交易
    RESUME_ACCOUNT = "resume_account"    # 恢复账户交易
    SUSPEND_ORDER = "suspend_order"      # 暂停报单
    RESUME_ORDER = "resume_order"        # 恢复报单
    WARNING = "warning"                  # 警告
    BLOCK_ORDER = "block_order"          # 拦截订单


@dataclass
class Order:
    """订单数据模型"""
    oid: int                # 订单唯一标识符
    account_id: str         # 交易账户编号
    contract_id: str        # 合约代码
    direction: Direction    # 买卖方向
    price: float           # 订单价格
    volume: int            # 订单数量
    timestamp: int         # 订单提交时间戳（纳秒级精度）


@dataclass
class Trade:
    """成交数据模型"""
    tid: int              # 成交唯一标识符
    oid: int              # 关联的订单ID
    price: float          # 成交价格
    volume: int           # 实际成交量
    timestamp: int        # 成交时间戳（纳秒级精度）
    
    # 冗余字段，方便查询
    account_id: Optional[str] = None
    contract_id: Optional[str] = None


@dataclass
class Action:
    """风控动作"""
    action_type: ActionType   # 动作类型
    target_id: str           # 目标ID（账户ID或合约ID）
    reason: str              # 触发原因
    timestamp: int           # 动作生成时间戳
    rule_name: str           # 触发的规则名称
    metadata: dict = None    # 额外的元数据
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}