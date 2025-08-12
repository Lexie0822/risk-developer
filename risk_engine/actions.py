from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Dict


class Action(Enum):
    """风控处置动作（可扩展）。"""

    # 账户与交易维度
    SUSPEND_ACCOUNT_TRADING = auto()  # 暂停账户交易（下单与成交相关操作）
    RESUME_ACCOUNT_TRADING = auto()  # 恢复账户交易

    # 报单维度
    SUSPEND_ORDERING = auto()  # 暂停报单
    RESUME_ORDERING = auto()  # 恢复报单

    # 精细化
    BLOCK_ORDER = auto()  # 拒绝单笔订单
    BLOCK_CANCEL = auto()  # 拒绝撤单

    # 风险提示
    ALERT = auto()  # 告警，仅提示不强制拦截


@dataclass(slots=True)
class EmittedAction:
    """兼容旧测试的动作记录：`type.name` 可用。"""

    type: Action
    account_id: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, object] = field(default_factory=dict)