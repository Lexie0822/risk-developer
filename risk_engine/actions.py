from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Action(str, Enum):
    PAUSE_TRADING = "PAUSE_TRADING"  # Pause both orders and trades for the account/product
    RESUME_TRADING = "RESUME_TRADING"
    PAUSE_ORDER = "PAUSE_ORDER"
    RESUME_ORDER = "RESUME_ORDER"


@dataclass(slots=True)
class ActionEvent:
    timestamp_ns: int
    account_id: str
    action: Action
    reason: str
    contract_id: Optional[str] = None
    product_id: Optional[str] = None