from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple, FrozenSet


# 维度键：采用不可变的 tuple 表达，便于作为 dict key 与最小化开销
DimensionKey = Tuple[Tuple[str, str], ...]

# 预计算常用维度键模式，避免运行时排序
_DIMENSION_PATTERNS = {
    # 单维度
    ('account_id',): lambda account_id: (('account_id', account_id),),
    ('contract_id',): lambda contract_id: (('contract_id', contract_id),),
    ('product_id',): lambda product_id: (('product_id', product_id),),
    
    # 双维度（按字母序预排序）
    ('account_id', 'contract_id'): lambda account_id, contract_id: (('account_id', account_id), ('contract_id', contract_id)),
    ('account_id', 'product_id'): lambda account_id, product_id: (('account_id', account_id), ('product_id', product_id)),
    
    # 三维度（常用组合）
    ('account_id', 'contract_id', 'product_id'): lambda account_id, contract_id, product_id: (
        ('account_id', account_id), ('contract_id', contract_id), ('product_id', product_id)
    ),
}

def make_dimension_key(**dims: Optional[str]) -> DimensionKey:
    """构造维度键。

    仅包含非空维度，维度为字符串键值对，最终排序后组成 tuple 以保证确定性。
    典型维度：account_id, contract_id, product_id, exchange_id, account_group_id
    
    优化：对常用模式使用预计算避免排序开销。
    """
    # 过滤非空维度
    non_empty = {k: v for k, v in dims.items() if v is not None}
    
    # 尝试匹配预计算模式
    keys = tuple(sorted(non_empty.keys()))
    if keys in _DIMENSION_PATTERNS:
        pattern_func = _DIMENSION_PATTERNS[keys]
        # 按预定义顺序传参
        args = [non_empty[k] for k in keys]
        return pattern_func(*args)
    
    # 回退到通用方法（运行时排序）
    items = [(k, v) for k, v in non_empty.items()]
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