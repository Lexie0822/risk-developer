from __future__ import annotations

from enum import Enum
from typing import Dict, Tuple, Iterable


class StatsDimension(str, Enum):
    ACCOUNT = "account"
    CONTRACT = "contract"
    PRODUCT = "product"


Key = Tuple[str, ...]


class MultiDimCounter:
    """A tiny, allocation-friendly multi-dimensional counter.

    Keys are tuples of strings, e.g. (account_id,), (account_id, contract_id) or
    (account_id, product_id) depending on configuration. This keeps lookups O(1)
    and makes it trivial to extend with more dimensions if needed.
    """

    __slots__ = ("_counters",)

    def __init__(self) -> None:
        self._counters: Dict[Key, int] = {}

    def add(self, key: Key, delta: int) -> int:
        new_value = self._counters.get(key, 0) + delta
        self._counters[key] = new_value
        return new_value

    def get(self, key: Key) -> int:
        return self._counters.get(key, 0)

    def reset_keys_with_prefix(self, prefix: Key) -> None:
        keys_to_delete = [k for k in self._counters if k[: len(prefix)] == prefix]
        for k in keys_to_delete:
            del self._counters[k]

    def items(self) -> Iterable[Tuple[Key, int]]:
        return self._counters.items()