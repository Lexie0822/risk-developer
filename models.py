from enum import Enum
from dataclasses import dataclass
from typing import Optional, List
import time


class Direction(Enum):
    """交易方向枚举"""
    BID = "Bid"  # 买入
    ASK = "Ask"  # 卖出


class ActionType(Enum):
    """风控处置指令类型"""
    SUSPEND_TRADING = "suspend_trading"  # 暂停交易
    SUSPEND_ORDER = "suspend_order"      # 暂停报单
    RESUME_TRADING = "resume_trading"    # 恢复交易
    RESUME_ORDER = "resume_order"        # 恢复报单
    ALERT = "alert"                      # 告警
    REJECT_ORDER = "reject_order"        # 拒绝订单


@dataclass
class Order:
    """订单数据结构"""
    oid: int                    # 订单唯一标识符
    account_id: str            # 交易账户编号
    contract_id: str           # 合约代码
    direction: Direction       # 买卖方向
    price: float               # 订单价格
    volume: int                # 订单数量
    timestamp: int             # 订单提交时间戳（纳秒级精度）


@dataclass
class Trade:
    """成交数据结构"""
    tid: int                   # 成交唯一标识符
    oid: int                   # 关联的订单ID
    price: float               # 成交价格
    volume: int                # 实际成交量
    timestamp: int             # 成交时间戳（纳秒级精度）


@dataclass
class Action:
    """风控处置指令"""
    action_type: ActionType    # 指令类型
    target_id: str            # 目标对象ID（账户ID、合约ID等）
    reason: str               # 触发原因
    timestamp: int            # 生成时间戳
    metadata: Optional[dict] = None  # 额外元数据


@dataclass
class RiskRule:
    """风控规则配置"""
    rule_id: str              # 规则ID
    rule_name: str            # 规则名称
    rule_type: str            # 规则类型
    enabled: bool             # 是否启用
    threshold: float          # 阈值
    time_window: int          # 时间窗口（秒）
    actions: List[ActionType] # 触发的动作列表
    metadata: dict            # 规则元数据（用于扩展参数）


def get_current_timestamp_ns() -> int:
    """获取当前纳秒级时间戳"""
    return int(time.time() * 1_000_000_000)