from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ActionType(str, Enum):
    SUSPEND_ACCOUNT_TRADING = "SUSPEND_ACCOUNT_TRADING"
    RESUME_ACCOUNT_TRADING = "RESUME_ACCOUNT_TRADING"
    SUSPEND_ORDERING = "SUSPEND_ORDERING"
    RESUME_ORDERING = "RESUME_ORDERING"
    BLOCK_ORDER = "BLOCK_ORDER"
    ALERT = "ALERT"


@dataclass(slots=True)
class Action:
    type: ActionType
    account_id: str
    reason: str
    until_ns: Optional[int] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def short(self) -> str:
        fields = {
            "type": self.type.value,
            "account": self.account_id,
            "reason": self.reason,
        }
        if self.until_ns is not None:
            fields["until_ns"] = self.until_ns
        if self.metadata:
            fields["meta"] = self.metadata
        return str(fields)