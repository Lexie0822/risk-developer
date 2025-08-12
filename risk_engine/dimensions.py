from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple, FrozenSet


# 维度键：采用不可变的 tuple 表达，便于作为 dict key 与最小化开销
DimensionKey = Tuple[Tuple[str, str], ...]


def make_dimension_key(**dims: Optional[str]) -> DimensionKey:
    """构造维度键。

    仅包含非空维度，维度为字符串键值对，最终排序后组成 tuple 以保证确定性。
    典型维度：account_id, contract_id, product_id, exchange_id, account_group_id
    """

    items = [(k, v) for k, v in dims.items() if v is not None]
    items.sort(key=lambda kv: kv[0])
    return tuple(items)


@dataclass(slots=True)
class InstrumentCatalog:
    """合约静态属性目录，用于合约 -> 产品 等静态映射查询。

    - 线程安全需求：初始化后只读，查询无锁。
    - 可扩展字段：交易所、品种、账户组策略等。
    """

    contract_to_product: Mapping[str, str]
    contract_to_exchange: Mapping[str, str]

    def resolve_dimensions(
        self,
        account_id: Optional[str],
        contract_id: Optional[str],
        exchange_id: Optional[str] = None,
        account_group_id: Optional[str] = None,
    ) -> DimensionKey:
        product_id = None
        ex = exchange_id
        if contract_id:
            product_id = self.contract_to_product.get(contract_id)
            ex = ex or self.contract_to_exchange.get(contract_id)
        return make_dimension_key(
            account_id=account_id,
            contract_id=contract_id,
            product_id=product_id,
            exchange_id=ex,
            account_group_id=account_group_id,
        )