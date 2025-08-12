from __future__ import annotations
import enum
from dataclasses import dataclass
from typing import Any, Mapping, Optional


class ActionType(enum.IntEnum):
    SUSPEND_ACCOUNT_TRADING = 1
    SUSPEND_ACCOUNT_ORDERING = 2
    RESUME_ACCOUNT_TRADING = 3
    RESUME_ACCOUNT_ORDERING = 4
    ALERT = 5


@dataclass(frozen=True, slots=True)
class ActionEvent:
    type: ActionType
    account_id: str
    timestamp: int
    reason: str
    extra: Optional[Mapping[str, Any]] = None