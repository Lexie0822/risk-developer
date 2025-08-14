"""
风控规则引擎
负责规则检查和Action生成
"""
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
import time
import threading
from collections import defaultdict

from .models import Order, Trade, Action
from .config import (RiskControlConfig, RiskRule, RuleCondition, 
                    ActionType, MetricType, DimensionType)
from .statistics import StatisticsEngine


class RiskControlEngine:
    """风控引擎主类"""
    
    def __init__(self, config: RiskControlConfig = None):
        """初始化风控引擎"""
        self.config = config or RiskControlConfig()
        self.statistics = StatisticsEngine()
        
        # 账户状态管理
        self._account_status: Dict[str, Set[ActionType]] = defaultdict(set)
        self._status_lock = threading.RLock()
        
        # Action处理器
        self._action_handlers = {}
        self._register_default_handlers()
        
        # 自动恢复管理
        self._recovery_timers: Dict[str, threading.Timer] = {}
    
    def _register_default_handlers(self):
        """注册默认的Action处理器"""
        self._action_handlers[ActionType.SUSPEND_TRADING] = self._handle_suspend_trading
        self._action_handlers[ActionType.SUSPEND_ORDER] = self._handle_suspend_order
        self._action_handlers[ActionType.RESUME_TRADING] = self._handle_resume_trading
        self._action_handlers[ActionType.RESUME_ORDER] = self._handle_resume_order
    
    def _handle_suspend_trading(self, action: Action):
        """处理暂停交易"""
        with self._status_lock:
            self._account_status[action.account_id].add(ActionType.SUSPEND_TRADING)
    
    def _handle_suspend_order(self, action: Action):
        """处理暂停报单"""
        with self._status_lock:
            self._account_status[action.account_id].add(ActionType.SUSPEND_ORDER)
        
        # 如果设置了duration，自动恢复
        duration = action.params.get('duration')
        if duration:
            self._schedule_recovery(action.account_id, ActionType.RESUME_ORDER, duration)
    
    def _handle_resume_trading(self, action: Action):
        """处理恢复交易"""
        with self._status_lock:
            self._account_status[action.account_id].discard(ActionType.SUSPEND_TRADING)
    
    def _handle_resume_order(self, action: Action):
        """处理恢复报单"""
        with self._status_lock:
            self._account_status[action.account_id].discard(ActionType.SUSPEND_ORDER)
    
    def _schedule_recovery(self, account_id: str, action_type: ActionType, delay_seconds: int):
        """调度自动恢复"""
        timer_key = f"{account_id}_{action_type.value}"
        
        # 取消之前的定时器
        if timer_key in self._recovery_timers:
            self._recovery_timers[timer_key].cancel()
        
        # 创建新的定时器
        def recover():
            action = Action(
                action_type=action_type.value,
                account_id=account_id,
                reason="自动恢复",
                timestamp=int(time.time() * 1_000_000_000)
            )
            self._execute_action(action)
            del self._recovery_timers[timer_key]
        
        timer = threading.Timer(delay_seconds, recover)
        timer.start()
        self._recovery_timers[timer_key] = timer
    
    def _check_condition(self, condition: RuleCondition, dimension_key: str, 
                        current_timestamp: int) -> bool:
        """检查单个条件是否满足"""
        # 获取统计值
        value = self.statistics.get_statistic(
            condition.dimension, 
            dimension_key,
            condition.metric_type,
            current_timestamp
        )
        
        # 比较操作
        comparisons = {
            "gt": lambda x, y: x > y,
            "lt": lambda x, y: x < y,
            "eq": lambda x, y: x == y,
            "gte": lambda x, y: x >= y,
            "lte": lambda x, y: x <= y,
        }
        
        compare_func = comparisons.get(condition.comparison)
        if not compare_func:
            return False
        
        return compare_func(value, condition.threshold)
    
    def _check_rule(self, rule: RiskRule, order: Order = None, 
                   trade: Trade = None) -> List[Action]:
        """检查规则是否触发"""
        if not rule.enabled:
            return []
        
        # 获取相关维度信息
        account_id = None
        contract_id = None
        current_timestamp = None
        
        if order:
            account_id = order.account_id
            contract_id = order.contract_id
            current_timestamp = order.timestamp
        elif trade:
            account_id = trade.account_id
            contract_id = trade.contract_id
            current_timestamp = trade.timestamp
        
        if not account_id or not current_timestamp:
            return []
        
        # 检查条件
        conditions_met = []
        for condition in rule.conditions:
            dimension_key = None
            
            # 根据维度类型确定key
            if condition.dimension == DimensionType.ACCOUNT:
                dimension_key = account_id
            elif condition.dimension == DimensionType.CONTRACT:
                dimension_key = contract_id
            elif condition.dimension == DimensionType.PRODUCT:
                from .config import get_product_by_contract
                dimension_key = get_product_by_contract(contract_id)
            
            if dimension_key:
                met = self._check_condition(condition, dimension_key, current_timestamp)
                conditions_met.append(met)
        
        # 根据逻辑关系判断是否触发
        if rule.logic == "AND":
            triggered = all(conditions_met) if conditions_met else False
        else:  # OR
            triggered = any(conditions_met) if conditions_met else False
        
        # 生成Actions
        if triggered:
            actions = []
            for rule_action in rule.actions:
                action = Action(
                    action_type=rule_action.action_type.value,
                    account_id=account_id,
                    contract_id=contract_id,
                    reason=f"{rule.name}: {rule_action.params.get('reason', '')}",
                    timestamp=current_timestamp,
                    params=rule_action.params
                )
                actions.append(action)
            return actions
        
        return []
    
    def _execute_action(self, action: Action):
        """执行Action"""
        action_type = ActionType(action.action_type)
        handler = self._action_handlers.get(action_type)
        if handler:
            handler(action)
    
    def process_order(self, order: Order) -> List[Action]:
        """处理订单事件"""
        # 检查账户状态
        with self._status_lock:
            account_status = self._account_status.get(order.account_id, set())
            if ActionType.SUSPEND_ORDER in account_status:
                # 账户报单被暂停，拒绝订单
                return [Action(
                    action_type="REJECT_ORDER",
                    account_id=order.account_id,
                    contract_id=order.contract_id,
                    reason="账户报单已被暂停",
                    timestamp=order.timestamp,
                    params={"order_id": order.oid}
                )]
        
        # 更新统计
        self.statistics.on_order(order)
        
        # 检查所有规则
        all_actions = []
        for rule in self.config.get_enabled_rules():
            actions = self._check_rule(rule, order=order)
            all_actions.extend(actions)
        
        # 执行Actions
        for action in all_actions:
            self._execute_action(action)
        
        return all_actions
    
    def process_trade(self, trade: Trade) -> List[Action]:
        """处理成交事件"""
        # 更新统计
        self.statistics.on_trade(trade)
        
        # 检查所有规则
        all_actions = []
        for rule in self.config.get_enabled_rules():
            actions = self._check_rule(rule, trade=trade)
            all_actions.extend(actions)
        
        # 执行Actions
        for action in all_actions:
            self._execute_action(action)
        
        return all_actions
    
    def get_account_status(self, account_id: str) -> Set[ActionType]:
        """获取账户当前状态"""
        with self._status_lock:
            return self._account_status.get(account_id, set()).copy()
    
    def is_account_suspended(self, account_id: str) -> bool:
        """检查账户是否被暂停交易"""
        status = self.get_account_status(account_id)
        return ActionType.SUSPEND_TRADING in status
    
    def is_order_suspended(self, account_id: str) -> bool:
        """检查账户是否被暂停报单"""
        status = self.get_account_status(account_id)
        return ActionType.SUSPEND_ORDER in status
    
    def reset(self):
        """重置引擎状态（用于测试）"""
        self.statistics.clear_statistics()
        with self._status_lock:
            self._account_status.clear()
        
        # 取消所有定时器
        for timer in self._recovery_timers.values():
            timer.cancel()
        self._recovery_timers.clear()