from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from models import Order, Trade, Action, ActionType, RiskRule, get_current_timestamp_ns
from statistics_engine import MultiDimensionalStatistics


class BaseRiskRule(ABC):
    """风控规则基类"""
    
    def __init__(self, rule_config: RiskRule):
        self.config = rule_config
        
    @abstractmethod
    def check(self, order: Order, trade: Optional[Trade], stats: MultiDimensionalStatistics) -> List[Action]:
        """检查规则是否触发，返回需要执行的动作列表"""
        pass
        
    def is_enabled(self) -> bool:
        """检查规则是否启用"""
        return self.config.enabled


class AccountTradingVolumeRule(BaseRiskRule):
    """单账户成交量限制规则"""
    
    def check(self, order: Order, trade: Optional[Trade], stats: MultiDimensionalStatistics) -> List[Action]:
        if not self.is_enabled() or not trade:
            return []
            
        current_time = get_current_timestamp_ns()
        account_id = order.account_id
        
        # 获取账户当日成交量
        current_volume = stats.get_account_trade_volume(account_id, current_time)
        
        # 检查是否超过阈值
        if current_volume > self.config.threshold:
            actions = []
            for action_type in self.config.actions:
                action = Action(
                    action_type=action_type,
                    target_id=account_id,
                    reason=f"账户 {account_id} 当日成交量 {current_volume} 超过阈值 {self.config.threshold}",
                    timestamp=current_time,
                    metadata={
                        "rule_id": self.config.rule_id,
                        "current_volume": current_volume,
                        "threshold": self.config.threshold
                    }
                )
                actions.append(action)
            return actions
            
        return []


class AccountTradingAmountRule(BaseRiskRule):
    """单账户成交金额限制规则"""
    
    def check(self, order: Order, trade: Optional[Trade], stats: MultiDimensionalStatistics) -> List[Action]:
        if not self.is_enabled() or not trade:
            return []
            
        current_time = get_current_timestamp_ns()
        account_id = order.account_id
        
        # 获取账户当日成交金额
        current_amount = stats.get_account_trade_amount(account_id, current_time)
        
        # 检查是否超过阈值
        if current_amount > self.config.threshold:
            actions = []
            for action_type in self.config.actions:
                action = Action(
                    action_type=action_type,
                    target_id=account_id,
                    reason=f"账户 {account_id} 当日成交金额 {current_amount:.2f} 超过阈值 {self.config.threshold}",
                    timestamp=current_time,
                    metadata={
                        "rule_id": self.config.rule_id,
                        "current_amount": current_amount,
                        "threshold": self.config.threshold
                    }
                )
                actions.append(action)
            return actions
            
        return []


class OrderFrequencyRule(BaseRiskRule):
    """报单频率控制规则"""
    
    def check(self, order: Order, trade: Optional[Trade], stats: MultiDimensionalStatistics) -> List[Action]:
        if not self.is_enabled():
            return []
            
        current_time = get_current_timestamp_ns()
        account_id = order.account_id
        
        # 获取时间窗口设置，默认为秒级
        time_window = self.config.time_window
        
        if time_window == 1:  # 每秒报单数检查
            current_frequency = stats.get_account_order_frequency_per_second(account_id, current_time)
        elif time_window == 60:  # 每分钟报单数检查
            current_frequency = stats.get_account_order_frequency_per_minute(account_id, current_time)
        else:
            # 其他时间窗口暂不支持，返回空
            return []
            
        # 检查是否超过阈值
        if current_frequency > self.config.threshold:
            actions = []
            for action_type in self.config.actions:
                time_unit = "秒" if time_window == 1 else "分钟"
                action = Action(
                    action_type=action_type,
                    target_id=account_id,
                    reason=f"账户 {account_id} 每{time_unit}报单数 {current_frequency} 超过阈值 {self.config.threshold}",
                    timestamp=current_time,
                    metadata={
                        "rule_id": self.config.rule_id,
                        "current_frequency": current_frequency,
                        "threshold": self.config.threshold,
                        "time_window": time_window
                    }
                )
                actions.append(action)
            return actions
            
        return []


class ContractPositionRule(BaseRiskRule):
    """合约持仓限制规则（可选扩展）"""
    
    def check(self, order: Order, trade: Optional[Trade], stats: MultiDimensionalStatistics) -> List[Action]:
        if not self.is_enabled() or not trade:
            return []
            
        current_time = get_current_timestamp_ns()
        contract_id = order.contract_id
        
        # 获取合约成交量
        current_volume = stats.get_contract_trade_volume(contract_id, current_time)
        
        # 检查是否超过阈值
        if current_volume > self.config.threshold:
            actions = []
            for action_type in self.config.actions:
                action = Action(
                    action_type=action_type,
                    target_id=contract_id,
                    reason=f"合约 {contract_id} 成交量 {current_volume} 超过阈值 {self.config.threshold}",
                    timestamp=current_time,
                    metadata={
                        "rule_id": self.config.rule_id,
                        "current_volume": current_volume,
                        "threshold": self.config.threshold
                    }
                )
                actions.append(action)
            return actions
            
        return []


class RiskRuleEngine:
    """风控规则引擎"""
    
    def __init__(self):
        self.rules: Dict[str, BaseRiskRule] = {}
        self.rule_classes = {
            "account_trading_volume": AccountTradingVolumeRule,
            "account_trading_amount": AccountTradingAmountRule,
            "order_frequency": OrderFrequencyRule,
            "contract_position": ContractPositionRule
        }
        
    def add_rule(self, rule_config: RiskRule) -> bool:
        """添加风控规则"""
        try:
            rule_class = self.rule_classes.get(rule_config.rule_type)
            if not rule_class:
                print(f"未知的规则类型: {rule_config.rule_type}")
                return False
                
            rule_instance = rule_class(rule_config)
            self.rules[rule_config.rule_id] = rule_instance
            return True
        except Exception as e:
            print(f"添加规则失败: {e}")
            return False
            
    def remove_rule(self, rule_id: str) -> bool:
        """移除风控规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
        
    def update_rule(self, rule_config: RiskRule) -> bool:
        """更新风控规则"""
        if rule_config.rule_id in self.rules:
            self.remove_rule(rule_config.rule_id)
        return self.add_rule(rule_config)
        
    def enable_rule(self, rule_id: str) -> bool:
        """启用规则"""
        if rule_id in self.rules:
            self.rules[rule_id].config.enabled = True
            return True
        return False
        
    def disable_rule(self, rule_id: str) -> bool:
        """禁用规则"""
        if rule_id in self.rules:
            self.rules[rule_id].config.enabled = False
            return True
        return False
        
    def check_all_rules(self, order: Order, trade: Optional[Trade], stats: MultiDimensionalStatistics) -> List[Action]:
        """检查所有规则，返回触发的动作列表"""
        all_actions = []
        
        for rule in self.rules.values():
            if rule.is_enabled():
                actions = rule.check(order, trade, stats)
                all_actions.extend(actions)
                
        return all_actions
        
    def get_rule_status(self) -> Dict[str, Dict]:
        """获取所有规则状态"""
        status = {}
        for rule_id, rule in self.rules.items():
            status[rule_id] = {
                "rule_name": rule.config.rule_name,
                "rule_type": rule.config.rule_type,
                "enabled": rule.config.enabled,
                "threshold": rule.config.threshold,
                "time_window": rule.config.time_window,
                "actions": [action.value for action in rule.config.actions]
            }
        return status