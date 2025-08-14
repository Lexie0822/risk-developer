"""
风控规则配置系统
"""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum
import json


class MetricType(Enum):
    """度量类型枚举"""
    TRADE_VOLUME = "trade_volume"          # 成交量
    TRADE_AMOUNT = "trade_amount"          # 成交金额
    ORDER_COUNT = "order_count"            # 报单量
    CANCEL_COUNT = "cancel_count"          # 撤单量
    ORDER_FREQUENCY = "order_frequency"    # 报单频率


class AggregationLevel(Enum):
    """聚合维度枚举"""
    ACCOUNT = "account"        # 账户维度
    CONTRACT = "contract"      # 合约维度
    PRODUCT = "product"        # 产品维度
    EXCHANGE = "exchange"      # 交易所维度
    ACCOUNT_GROUP = "account_group"  # 账户组维度


@dataclass
class RuleConfig:
    """风控规则配置基类"""
    rule_name: str                    # 规则名称
    enabled: bool = True              # 是否启用
    priority: int = 0                 # 优先级（数字越大优先级越高）
    description: str = ""             # 规则描述
    actions: List[str] = field(default_factory=list)  # 触发的动作列表


class VolumeControlConfig(RuleConfig):
    """成交量控制规则配置"""
    def __init__(self, 
                 rule_name: str,
                 metric_type: MetricType,
                 threshold: float,
                 aggregation_level: AggregationLevel,
                 time_window: Optional[int] = None,
                 target_ids: List[str] = None,
                 enabled: bool = True,
                 priority: int = 0,
                 description: str = "",
                 actions: List[str] = None):
        super().__init__(rule_name, enabled, priority, description, actions or [])
        self.metric_type = metric_type
        self.threshold = threshold
        self.aggregation_level = aggregation_level
        self.time_window = time_window
        self.target_ids = target_ids or []


class FrequencyControlConfig(RuleConfig):
    """频率控制规则配置"""
    def __init__(self,
                 rule_name: str,
                 max_count: int,
                 time_window: int,
                 aggregation_level: AggregationLevel,
                 auto_resume: bool = True,
                 target_ids: List[str] = None,
                 enabled: bool = True,
                 priority: int = 0,
                 description: str = "",
                 actions: List[str] = None):
        super().__init__(rule_name, enabled, priority, description, actions or [])
        self.max_count = max_count
        self.time_window = time_window
        self.aggregation_level = aggregation_level
        self.auto_resume = auto_resume
        self.target_ids = target_ids or []


@dataclass
class ProductConfig:
    """产品配置"""
    product_id: str                   # 产品ID
    product_name: str                 # 产品名称
    contracts: List[str]              # 包含的合约列表
    exchange: str                     # 交易所


class RiskControlConfig:
    """风控系统总配置"""
    
    def __init__(self):
        self.rules: Dict[str, RuleConfig] = {}
        self.products: Dict[str, ProductConfig] = {}
        self.global_settings = {
            "enable_risk_control": True,
            "log_level": "INFO",
            "performance_mode": True,  # 高性能模式
            "max_rules_per_event": 100,  # 每个事件最多执行的规则数
        }
    
    def add_rule(self, rule: RuleConfig):
        """添加风控规则"""
        self.rules[rule.rule_name] = rule
    
    def remove_rule(self, rule_name: str):
        """移除风控规则"""
        if rule_name in self.rules:
            del self.rules[rule_name]
    
    def get_rule(self, rule_name: str) -> Optional[RuleConfig]:
        """获取风控规则"""
        return self.rules.get(rule_name)
    
    def get_enabled_rules(self) -> List[RuleConfig]:
        """获取所有启用的规则"""
        return [rule for rule in self.rules.values() if rule.enabled]
    
    def add_product(self, product: ProductConfig):
        """添加产品配置"""
        self.products[product.product_id] = product
    
    def get_product_by_contract(self, contract_id: str) -> Optional[ProductConfig]:
        """根据合约ID获取产品配置"""
        for product in self.products.values():
            if contract_id in product.contracts:
                return product
        return None
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "rules": {name: rule.__dict__ for name, rule in self.rules.items()},
            "products": {pid: product.__dict__ for pid, product in self.products.items()},
            "global_settings": self.global_settings
        }
    
    def save_to_file(self, filepath: str):
        """保存配置到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'RiskControlConfig':
        """从文件加载配置"""
        config = cls()
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 加载全局设置
        config.global_settings.update(data.get("global_settings", {}))
        
        # 加载产品配置
        for pid, pdata in data.get("products", {}).items():
            product = ProductConfig(**pdata)
            config.products[pid] = product
        
        # 加载规则配置（这里需要根据规则类型创建不同的配置对象）
        # 实际使用时可以通过规则类型字段来判断
        
        return config


def create_default_config() -> RiskControlConfig:
    """创建默认配置"""
    config = RiskControlConfig()
    
    # 添加产品配置示例
    t_futures = ProductConfig(
        product_id="T_FUTURES",
        product_name="10年期国债期货",
        contracts=["T2303", "T2306", "T2309", "T2312"],
        exchange="CFFEX"  # 中金所
    )
    config.add_product(t_futures)
    
    # 添加单账户成交量限制规则
    volume_rule = VolumeControlConfig(
        rule_name="daily_volume_limit",
        description="单账户日成交量限制",
        metric_type=MetricType.TRADE_VOLUME,
        threshold=1000,  # 1000手
        aggregation_level=AggregationLevel.ACCOUNT,
        actions=["suspend_account"],
        priority=10
    )
    config.add_rule(volume_rule)
    
    # 添加报单频率控制规则
    frequency_rule = FrequencyControlConfig(
        rule_name="order_frequency_control",
        description="报单频率控制",
        max_count=50,  # 50次
        time_window=1,  # 1秒
        aggregation_level=AggregationLevel.ACCOUNT,
        actions=["suspend_order"],
        auto_resume=True,
        priority=20
    )
    config.add_rule(frequency_rule)
    
    return config