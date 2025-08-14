from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    """买卖方向。"""

    BID = "Bid"
    ASK = "Ask"


class OrderStatus(str, Enum):
    """订单状态。"""
    
    PENDING = "Pending"        # 待处理
    PARTIAL_FILLED = "PartialFilled"  # 部分成交
    FILLED = "Filled"          # 全部成交
    CANCELLED = "Cancelled"    # 已撤销
    REJECTED = "Rejected"      # 已拒绝


@dataclass(slots=True)
class Order:
    """订单输入模型（纳秒级时间戳）。
    
    字段完全符合需求规范：
    - oid: uint64_t -> int (Python中int可表示任意大小整数)
    - account_id: string
    - contract_id: string  
    - direction: enum (Bid/Ask)
    - price: double -> float
    - volume: int32_t -> int
    - timestamp: uint64_t -> int (纳秒级精度)
    
    扩展字段支持多维度统计。
    """

    oid: int  # uint64_t 订单唯一标识符
    account_id: str  # string 交易账户编号
    contract_id: str  # string 合约代码
    direction: Direction  # enum 买卖方向
    price: float  # double 订单价格
    volume: int  # int32_t 订单数量
    timestamp: int  # uint64_t 订单提交时间戳（纳秒级精度）
    # 扩展维度字段
    exchange_id: Optional[str] = None  # 交易所编号
    account_group_id: Optional[str] = None  # 账户组编号
    # 订单状态和业务字段
    status: OrderStatus = OrderStatus.PENDING  # 订单状态
    order_type: Optional[str] = None  # 订单类型（限价、市价等）


@dataclass(slots=True)
class Trade:
    """成交输入模型（纳秒级时间戳）。
    
    字段完全符合需求规范：
    - tid: uint64_t -> int
    - oid: uint64_t -> int  
    - price: double -> float
    - volume: int32_t -> int
    - timestamp: uint64_t -> int (纳秒级精度)
    
    为兼容性，account_id与contract_id为可选，将在引擎中通过oid补全。
    """

    tid: int  # uint64_t 成交唯一标识符
    oid: int  # uint64_t 关联的订单ID
    price: float  # double 成交价格
    volume: int  # int32_t 实际成交量
    timestamp: int  # uint64_t 成交时间戳（纳秒级精度）
    # 从关联订单补全的字段
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None


@dataclass(slots=True)
class CancelOrder:
    """撤单输入模型。
    
    用于监控撤单量统计，满足扩展点需求。
    """
    
    cancel_id: int  # uint64_t 撤单唯一标识符
    oid: int  # uint64_t 被撤销的订单ID
    timestamp: int  # uint64_t 撤单时间戳（纳秒级精度）
    # 从关联订单补全的字段
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None
    cancel_volume: Optional[int] = None  # 撤销数量


@dataclass(slots=True)
class ContractMetadata:
    contract_id: str
    product_id: str  # e.g. all T23xx belong to product "T"


class ProductResolver:
    """Resolve product_id from contract_id using a user-provided mapping.

    In real systems this would come from static reference data (instrument master).
    Here we keep a simple in-memory mapping with O(1) lookups.
    """

    def __init__(self, contract_to_product: Optional[dict[str, str]] = None) -> None:
        self._contract_to_product: dict[str, str] = contract_to_product or {}

    def set_mapping(self, mapping: dict[str, str]) -> None:
        self._contract_to_product = dict(mapping)

    def update_mapping(self, contract_id: str, product_id: str) -> None:
        self._contract_to_product[contract_id] = product_id

    def resolve_product(self, contract_id: str) -> Optional[str]:
        return self._contract_to_product.get(contract_id)