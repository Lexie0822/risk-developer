from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Tuple, FrozenSet, Any, Set
from abc import ABC, abstractmethod


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


class DimensionResolver(ABC):
    """维度解析器接口，支持扩展新的维度类型。"""
    
    @abstractmethod
    def resolve(self, key: str, value: str) -> Optional[str]:
        """解析维度值，返回规范化后的值。"""
        pass
    
    @abstractmethod
    def get_supported_dimensions(self) -> Set[str]:
        """获取支持的维度类型集合。"""
        pass


class StandardDimensionResolver(DimensionResolver):
    """标准维度解析器，支持内置维度类型。"""
    
    def __init__(self):
        self._supported = {
            "account_id", "contract_id", "product_id", 
            "exchange_id", "account_group_id"
        }
    
    def resolve(self, key: str, value: str) -> Optional[str]:
        if key in self._supported:
            return value
        return None
    
    def get_supported_dimensions(self) -> Set[str]:
        return self._supported.copy()


class ExtensibleDimensionResolver(DimensionResolver):
    """可扩展维度解析器，支持动态添加新维度。"""
    
    def __init__(self, base_resolver: Optional[DimensionResolver] = None):
        self._base = base_resolver or StandardDimensionResolver()
        self._custom_resolvers: Dict[str, callable] = {}
        self._custom_dimensions: Set[str] = set()
    
    def add_dimension(self, dimension_name: str, resolver_func: Optional[callable] = None):
        """添加新维度支持。
        
        Args:
            dimension_name: 维度名称
            resolver_func: 可选的值解析函数，默认直接返回原值
        """
        self._custom_dimensions.add(dimension_name)
        if resolver_func:
            self._custom_resolvers[dimension_name] = resolver_func
    
    def resolve(self, key: str, value: str) -> Optional[str]:
        # 先尝试基础解析器
        result = self._base.resolve(key, value)
        if result is not None:
            return result
        
        # 尝试自定义维度
        if key in self._custom_dimensions:
            resolver = self._custom_resolvers.get(key)
            if resolver:
                return resolver(value)
            return value  # 默认直接返回
        
        return None
    
    def get_supported_dimensions(self) -> Set[str]:
        return self._base.get_supported_dimensions() | self._custom_dimensions


@dataclass(slots=True)
class InstrumentCatalog:
    """合约静态属性目录，用于合约 -> 产品 等静态映射查询。

    - 线程安全需求：初始化后只读，查询无锁。
    - 可扩展字段：交易所、品种、账户组策略等。
    - 支持动态维度扩展。
    """

    contract_to_product: Mapping[str, str]
    contract_to_exchange: Mapping[str, str]
    # 扩展维度映射
    contract_to_sector: Optional[Mapping[str, str]] = None  # 行业分类
    account_to_group: Optional[Mapping[str, str]] = None    # 账户分组
    dimension_resolver: Optional[DimensionResolver] = None   # 维度解析器

    def __post_init__(self):
        if self.dimension_resolver is None:
            # 使用可扩展解析器作为默认
            resolver = ExtensibleDimensionResolver()
            # 添加行业分类维度
            if self.contract_to_sector:
                resolver.add_dimension("sector_id")
            object.__setattr__(self, 'dimension_resolver', resolver)

    def resolve_dimensions(
        self,
        account_id: Optional[str],
        contract_id: Optional[str],
        exchange_id: Optional[str] = None,
        account_group_id: Optional[str] = None,
        **extra_dims: Optional[str]
    ) -> DimensionKey:
        """解析维度信息，支持扩展维度。"""
        product_id = None
        sector_id = None
        ex = exchange_id
        ag = account_group_id
        
        if contract_id:
            product_id = self.contract_to_product.get(contract_id)
            ex = ex or self.contract_to_exchange.get(contract_id)
            if self.contract_to_sector:
                sector_id = self.contract_to_sector.get(contract_id)
        
        if account_id and self.account_to_group and not ag:
            ag = self.account_to_group.get(account_id)
        
        # 构建基础维度
        base_dims = {
            "account_id": account_id,
            "contract_id": contract_id,
            "product_id": product_id,
            "exchange_id": ex,
            "account_group_id": ag,
            "sector_id": sector_id,
        }
        
        # 添加扩展维度
        if extra_dims and self.dimension_resolver:
            for key, value in extra_dims.items():
                if value is not None and self.dimension_resolver.resolve(key, value) is not None:
                    base_dims[key] = value
        
        return make_dimension_key(**base_dims)
    
    def add_custom_dimension_mapping(self, dimension: str, mapping: Mapping[str, str]):
        """添加自定义维度映射。"""
        setattr(self, f"_{dimension}_mapping", mapping)
        if self.dimension_resolver and isinstance(self.dimension_resolver, ExtensibleDimensionResolver):
            self.dimension_resolver.add_dimension(dimension)
    
    def get_custom_dimension_value(self, dimension: str, key: str) -> Optional[str]:
        """获取自定义维度值。"""
        mapping = getattr(self, f"_{dimension}_mapping", None)
        if mapping:
            return mapping.get(key)
        return None


class DimensionExtensionRegistry:
    """维度扩展注册表，用于全局管理维度扩展。"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._dimension_factories: Dict[str, callable] = {}
            self._dimension_validators: Dict[str, callable] = {}
            self._initialized = True
    
    def register_dimension(self, name: str, factory: callable, validator: Optional[callable] = None):
        """注册新维度类型。
        
        Args:
            name: 维度名称
            factory: 维度值工厂函数
            validator: 可选的验证函数
        """
        self._dimension_factories[name] = factory
        if validator:
            self._dimension_validators[name] = validator
    
    def create_dimension_value(self, name: str, *args, **kwargs) -> Any:
        """创建维度值。"""
        factory = self._dimension_factories.get(name)
        if factory:
            return factory(*args, **kwargs)
        raise ValueError(f"Unknown dimension type: {name}")
    
    def validate_dimension_value(self, name: str, value: Any) -> bool:
        """验证维度值。"""
        validator = self._dimension_validators.get(name)
        if validator:
            return validator(value)
        return True  # 默认通过验证
    
    def get_registered_dimensions(self) -> Set[str]:
        """获取已注册的维度类型。"""
        return set(self._dimension_factories.keys())


# 全局注册表实例
dimension_registry = DimensionExtensionRegistry()

# 注册标准维度
dimension_registry.register_dimension("exchange_id", lambda x: x)
dimension_registry.register_dimension("account_group_id", lambda x: x)
dimension_registry.register_dimension("sector_id", lambda x: x)
dimension_registry.register_dimension("strategy_id", lambda x: x)  # 策略维度
dimension_registry.register_dimension("trader_id", lambda x: x)    # 交易员维度