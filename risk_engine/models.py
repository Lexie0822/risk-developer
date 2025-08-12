from __future__ import annotations
import enum
from dataclasses import dataclass


class Direction(enum.IntEnum):
    BID = 1
    ASK = 2


@dataclass(slots=True, frozen=True)
class Order:
    oid: int
    account_id: str
    contract_id: str
    direction: Direction
    price: float
    volume: int
    timestamp: int  # ns


@dataclass(slots=True, frozen=True)
class Trade:
    tid: int
    oid: int
    price: float
    volume: int
    timestamp: int  # ns


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