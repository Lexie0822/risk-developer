from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Direction(str, Enum):
    """买卖方向。"""

    BID = "Bid"
    ASK = "Ask"


@dataclass(slots=True)
class Order:
    """订单输入模型（纳秒级时间戳）。

    - 注：为满足高吞吐与低延迟，使用 `slots=True` 降低内存与属性查找开销。
    """

    oid: int
    account_id: str
    contract_id: str
    direction: Direction
    price: float
    volume: int
    timestamp: int  # 纳秒
    exchange_id: Optional[str] = None  # 扩展维度：交易所
    account_group_id: Optional[str] = None  # 扩展维度：账户组


@dataclass(slots=True)
class Trade:
    """成交输入模型（纳秒级时间戳）。

    - 为兼容旧版测试，`account_id` 与 `contract_id` 为可选，将在引擎中通过 `oid` 补全。
    """

    tid: int
    oid: int
    price: float
    volume: int
    timestamp: int  # 纳秒
    account_id: Optional[str] = None
    contract_id: Optional[str] = None
    exchange_id: Optional[str] = None
    account_group_id: Optional[str] = None


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