"""
风控规则配置模块
支持动态配置和扩展的风控规则定义
"""
from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


class ActionType(Enum):
    """风控动作类型"""
    SUSPEND_TRADING = "suspend_trading"  # 暂停账户交易
    SUSPEND_ORDER = "suspend_order"      # 暂停报单
    RESUME_TRADING = "resume_trading"    # 恢复交易
    RESUME_ORDER = "resume_order"        # 恢复报单
    WARNING = "warning"                  # 警告
    BLOCK_ACCOUNT = "block_account"      # 冻结账户


class MetricType(Enum):
    """统计指标类型"""
    TRADE_VOLUME = "trade_volume"        # 成交量
    TRADE_AMOUNT = "trade_amount"        # 成交金额
    ORDER_COUNT = "order_count"          # 报单量
    CANCEL_COUNT = "cancel_count"        # 撤单量
    ORDER_FREQUENCY = "order_frequency"  # 报单频率


class DimensionType(Enum):
    """统计维度类型"""
    ACCOUNT = "account"          # 账户维度
    CONTRACT = "contract"        # 合约维度
    PRODUCT = "product"          # 产品维度
    EXCHANGE = "exchange"        # 交易所维度
    ACCOUNT_GROUP = "account_group"  # 账户组维度


@dataclass
class RuleCondition:
    """规则条件定义"""
    metric_type: MetricType
    threshold: float
    comparison: str  # "gt", "lt", "eq", "gte", "lte"
    time_window: Optional[int] = None  # 时间窗口（秒）
    dimension: DimensionType = DimensionType.ACCOUNT


@dataclass
class RuleAction:
    """规则动作定义"""
    action_type: ActionType
    params: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # 优先级，数值越大优先级越高


@dataclass
class RiskRule:
    """风控规则定义"""
    rule_id: str
    name: str
    description: str
    conditions: List[RuleCondition]
    actions: List[RuleAction]
    enabled: bool = True
    logic: str = "AND"  # 条件逻辑关系：AND/OR


class RiskControlConfig:
    """风控配置管理器"""
    
    def __init__(self):
        self.rules: Dict[str, RiskRule] = {}
        self._load_default_rules()
    
    def _load_default_rules(self):
        """加载默认规则"""
        # 单账户成交量限制规则
        volume_limit_rule = RiskRule(
            rule_id="VOLUME_LIMIT_001",
            name="单账户日成交量限制",
            description="当账户当日成交量超过1000手时，暂停该账户交易",
            conditions=[
                RuleCondition(
                    metric_type=MetricType.TRADE_VOLUME,
                    threshold=1000,
                    comparison="gt",
                    dimension=DimensionType.ACCOUNT
                )
            ],
            actions=[
                RuleAction(
                    action_type=ActionType.SUSPEND_TRADING,
                    params={"reason": "日成交量超限"},
                    priority=10
                )
            ]
        )
        
        # 报单频率控制规则
        order_freq_rule = RiskRule(
            rule_id="ORDER_FREQ_001",
            name="报单频率控制",
            description="账户每秒报单数超过50次时，暂停报单",
            conditions=[
                RuleCondition(
                    metric_type=MetricType.ORDER_FREQUENCY,
                    threshold=50,
                    comparison="gt",
                    time_window=1,  # 1秒窗口
                    dimension=DimensionType.ACCOUNT
                )
            ],
            actions=[
                RuleAction(
                    action_type=ActionType.SUSPEND_ORDER,
                    params={"duration": 60, "reason": "报单频率过高"},
                    priority=8
                )
            ]
        )
        
        self.add_rule(volume_limit_rule)
        self.add_rule(order_freq_rule)
    
    def add_rule(self, rule: RiskRule):
        """添加规则"""
        self.rules[rule.rule_id] = rule
    
    def update_rule(self, rule_id: str, **kwargs):
        """更新规则配置"""
        if rule_id in self.rules:
            rule = self.rules[rule_id]
            for key, value in kwargs.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
    
    def get_rule(self, rule_id: str) -> Optional[RiskRule]:
        """获取规则"""
        return self.rules.get(rule_id)
    
    def get_enabled_rules(self) -> List[RiskRule]:
        """获取所有启用的规则"""
        return [rule for rule in self.rules.values() if rule.enabled]
    
    def disable_rule(self, rule_id: str):
        """禁用规则"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = False
    
    def enable_rule(self, rule_id: str):
        """启用规则"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = True


# 产品与合约映射配置
PRODUCT_CONTRACT_MAPPING = {
    "T": ["T2303", "T2306", "T2309", "T2312"],  # 10年期国债期货
    "TF": ["TF2303", "TF2306", "TF2309", "TF2312"],  # 5年期国债期货
    "TS": ["TS2303", "TS2306", "TS2309", "TS2312"],  # 2年期国债期货
}


def get_product_by_contract(contract_id: str) -> Optional[str]:
    """根据合约代码获取产品代码"""
    for product, contracts in PRODUCT_CONTRACT_MAPPING.items():
        if contract_id in contracts:
            return product
    # 如果没有找到，尝试从合约代码中提取
    for i in range(len(contract_id)):
        if contract_id[i].isdigit():
            return contract_id[:i]
    return None