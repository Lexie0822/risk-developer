import json
import os
from typing import Dict, List, Optional
from models import RiskRule, ActionType


class RiskConfigManager:
    """风控规则配置管理器"""
    
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or "risk_rules.json"
        self.rules_config: Dict[str, RiskRule] = {}
        
    def load_config(self) -> bool:
        """从配置文件加载规则"""
        try:
            if not os.path.exists(self.config_file):
                self._create_default_config()
                
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            self.rules_config = {}
            for rule_data in config_data.get('rules', []):
                rule = self._parse_rule_config(rule_data)
                if rule:
                    self.rules_config[rule.rule_id] = rule
                    
            return True
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return False
            
    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            config_data = {
                "rules": [self._rule_to_dict(rule) for rule in self.rules_config.values()]
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
                
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
            
    def _parse_rule_config(self, rule_data: dict) -> Optional[RiskRule]:
        """解析规则配置"""
        try:
            # 解析动作类型
            actions = []
            for action_str in rule_data.get('actions', []):
                try:
                    actions.append(ActionType(action_str))
                except ValueError:
                    print(f"未知的动作类型: {action_str}")
                    continue
                    
            rule = RiskRule(
                rule_id=rule_data['rule_id'],
                rule_name=rule_data['rule_name'],
                rule_type=rule_data['rule_type'],
                enabled=rule_data.get('enabled', True),
                threshold=float(rule_data['threshold']),
                time_window=int(rule_data.get('time_window', 86400)),
                actions=actions,
                metadata=rule_data.get('metadata', {})
            )
            return rule
        except Exception as e:
            print(f"解析规则配置失败: {e}")
            return None
            
    def _rule_to_dict(self, rule: RiskRule) -> dict:
        """将规则转换为字典"""
        return {
            "rule_id": rule.rule_id,
            "rule_name": rule.rule_name,
            "rule_type": rule.rule_type,
            "enabled": rule.enabled,
            "threshold": rule.threshold,
            "time_window": rule.time_window,
            "actions": [action.value for action in rule.actions],
            "metadata": rule.metadata
        }
        
    def _create_default_config(self):
        """创建默认配置文件"""
        default_rules = [
            {
                "rule_id": "account_volume_limit_1000",
                "rule_name": "账户日内成交量限制1000手",
                "rule_type": "account_trading_volume",
                "enabled": True,
                "threshold": 1000,
                "time_window": 86400,
                "actions": ["suspend_trading", "alert"],
                "metadata": {
                    "description": "限制单账户日内成交量不超过1000手",
                    "priority": "high"
                }
            },
            {
                "rule_id": "account_amount_limit_1000000",
                "rule_name": "账户日内成交金额限制100万",
                "rule_type": "account_trading_amount",
                "enabled": True,
                "threshold": 1000000,
                "time_window": 86400,
                "actions": ["suspend_trading", "alert"],
                "metadata": {
                    "description": "限制单账户日内成交金额不超过100万",
                    "priority": "high"
                }
            },
            {
                "rule_id": "order_frequency_50_per_second",
                "rule_name": "报单频率每秒50次限制",
                "rule_type": "order_frequency",
                "enabled": True,
                "threshold": 50,
                "time_window": 1,
                "actions": ["suspend_order", "alert"],
                "metadata": {
                    "description": "限制单账户每秒报单数不超过50次",
                    "priority": "medium"
                }
            },
            {
                "rule_id": "order_frequency_500_per_minute",
                "rule_name": "报单频率每分钟500次限制",
                "rule_type": "order_frequency",
                "enabled": True,
                "threshold": 500,
                "time_window": 60,
                "actions": ["suspend_order", "alert"],
                "metadata": {
                    "description": "限制单账户每分钟报单数不超过500次",
                    "priority": "medium"
                }
            },
            {
                "rule_id": "contract_volume_limit_5000",
                "rule_name": "合约成交量限制5000手",
                "rule_type": "contract_position",
                "enabled": False,
                "threshold": 5000,
                "time_window": 86400,
                "actions": ["alert"],
                "metadata": {
                    "description": "监控单合约成交量，超过5000手时告警",
                    "priority": "low"
                }
            }
        ]
        
        config_data = {"rules": default_rules}
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            
    def get_rule(self, rule_id: str) -> Optional[RiskRule]:
        """获取指定规则"""
        return self.rules_config.get(rule_id)
        
    def get_all_rules(self) -> List[RiskRule]:
        """获取所有规则"""
        return list(self.rules_config.values())
        
    def add_rule(self, rule: RiskRule) -> bool:
        """添加新规则"""
        self.rules_config[rule.rule_id] = rule
        return self.save_config()
        
    def update_rule(self, rule: RiskRule) -> bool:
        """更新规则"""
        if rule.rule_id in self.rules_config:
            self.rules_config[rule.rule_id] = rule
            return self.save_config()
        return False
        
    def remove_rule(self, rule_id: str) -> bool:
        """删除规则"""
        if rule_id in self.rules_config:
            del self.rules_config[rule_id]
            return self.save_config()
        return False
        
    def enable_rule(self, rule_id: str) -> bool:
        """启用规则"""
        if rule_id in self.rules_config:
            self.rules_config[rule_id].enabled = True
            return self.save_config()
        return False
        
    def disable_rule(self, rule_id: str) -> bool:
        """禁用规则"""
        if rule_id in self.rules_config:
            self.rules_config[rule_id].enabled = False
            return self.save_config()
        return False
        
    def validate_config(self) -> List[str]:
        """验证配置的有效性"""
        errors = []
        
        for rule in self.rules_config.values():
            # 检查必填字段
            if not rule.rule_id:
                errors.append("规则ID不能为空")
            if not rule.rule_name:
                errors.append(f"规则 {rule.rule_id} 的名称不能为空")
            if rule.threshold <= 0:
                errors.append(f"规则 {rule.rule_id} 的阈值必须大于0")
            if rule.time_window <= 0:
                errors.append(f"规则 {rule.rule_id} 的时间窗口必须大于0")
            if not rule.actions:
                errors.append(f"规则 {rule.rule_id} 必须至少配置一个动作")
                
        return errors
        
    def reload_config(self) -> bool:
        """重新加载配置文件"""
        return self.load_config()