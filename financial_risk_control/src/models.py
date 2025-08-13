"""
Data models for the financial risk control system.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, List, Dict, Any
import time


class Direction(Enum):
    """Trading direction"""
    BID = "Bid"
    ASK = "Ask"


class ActionType(Enum):
    """Risk control action types"""
    SUSPEND_ACCOUNT = auto()  # 暂停账户交易
    SUSPEND_ORDER = auto()    # 暂停报单
    RESUME_ACCOUNT = auto()   # 恢复账户交易
    RESUME_ORDER = auto()     # 恢复报单
    WARNING = auto()          # 风险预警
    REDUCE_POSITION = auto()  # 减仓
    FREEZE_POSITION = auto()  # 冻结持仓
    

@dataclass
class Order:
    """Order data structure"""
    oid: int  # Order ID (uint64_t)
    account_id: str  # Account ID
    contract_id: str  # Contract ID (e.g., "T2303")
    direction: Direction  # Buy/Sell direction
    price: float  # Order price
    volume: int  # Order volume (int32_t)
    timestamp: int  # Timestamp in nanoseconds (uint64_t)
    
    @property
    def product_id(self) -> str:
        """Extract product ID from contract ID (e.g., "T2303" -> "T")"""
        # 简化处理：取合约代码的字母部分作为产品ID
        import re
        match = re.match(r'^([A-Za-z]+)', self.contract_id)
        return match.group(1) if match else self.contract_id
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'oid': self.oid,
            'account_id': self.account_id,
            'contract_id': self.contract_id,
            'direction': self.direction.value,
            'price': self.price,
            'volume': self.volume,
            'timestamp': self.timestamp
        }


@dataclass
class Trade:
    """Trade data structure"""
    tid: int  # Trade ID (uint64_t)
    oid: int  # Related Order ID (uint64_t)
    price: float  # Trade price
    volume: int  # Trade volume (int32_t)
    timestamp: int  # Timestamp in nanoseconds (uint64_t)
    
    # Additional fields for risk control
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    
    @property
    def product_id(self) -> str:
        """Extract product ID from contract ID"""
        if not self.contract_id:
            return ""
        import re
        match = re.match(r'^([A-Za-z]+)', self.contract_id)
        return match.group(1) if match else self.contract_id
    
    @property
    def amount(self) -> float:
        """Calculate trade amount"""
        return self.price * self.volume
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'tid': self.tid,
            'oid': self.oid,
            'price': self.price,
            'volume': self.volume,
            'timestamp': self.timestamp,
            'account_id': self.account_id,
            'contract_id': self.contract_id
        }


@dataclass
class Action:
    """Risk control action"""
    action_type: ActionType
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    product_id: Optional[str] = None
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(time.time() * 1e9))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'action_type': self.action_type.name,
            'account_id': self.account_id,
            'contract_id': self.contract_id,
            'product_id': self.product_id,
            'reason': self.reason,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }
    
    def __str__(self) -> str:
        """String representation"""
        return (f"Action({self.action_type.name}, account={self.account_id}, "
                f"contract={self.contract_id}, reason='{self.reason}')")


@dataclass
class RiskEvent:
    """Risk event for logging and monitoring"""
    event_type: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    description: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: int = field(default_factory=lambda: int(time.time() * 1e9))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'event_type': self.event_type,
            'severity': self.severity,
            'account_id': self.account_id,
            'contract_id': self.contract_id,
            'description': self.description,
            'metrics': self.metrics,
            'timestamp': self.timestamp
        }