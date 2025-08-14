"""
风控规则实现
"""
from typing import List, Optional, Dict, Set
from abc import ABC, abstractmethod
import time
from threading import Lock

from .models import Order, Trade, Action, ActionType
from .config import RuleConfig, VolumeControlConfig, FrequencyControlConfig, MetricType, AggregationLevel
from .statistics import StatisticsEngine


class RiskRule(ABC):
    """风控规则基类"""
    
    def __init__(self, config: RuleConfig, stats_engine: StatisticsEngine):
        self.config = config
        self.stats_engine = stats_engine
        self.suspended_targets: Dict[str, int] = {}  # target_id -> suspend_timestamp
        self.lock = Lock()
    
    @abstractmethod
    def check_order(self, order: Order) -> List[Action]:
        """检查订单是否违反规则"""
        pass
    
    @abstractmethod
    def check_trade(self, trade: Trade, order: Optional[Order] = None) -> List[Action]:
        """检查成交是否违反规则"""
        pass
    
    def is_target_suspended(self, target_id: str) -> bool:
        """检查目标是否被暂停"""
        with self.lock:
            return target_id in self.suspended_targets
    
    def suspend_target(self, target_id: str, timestamp: int):
        """暂停目标"""
        with self.lock:
            self.suspended_targets[target_id] = timestamp
    
    def resume_target(self, target_id: str):
        """恢复目标"""
        with self.lock:
            if target_id in self.suspended_targets:
                del self.suspended_targets[target_id]


class VolumeControlRule(RiskRule):
    """成交量控制规则"""
    
    def __init__(self, config: VolumeControlConfig, stats_engine: StatisticsEngine):
        super().__init__(config, stats_engine)
        self.volume_config = config
    
    def check_order(self, order: Order) -> List[Action]:
        """订单检查（成交量规则不检查订单）"""
        return []
    
    def check_trade(self, trade: Trade, order: Optional[Order] = None) -> List[Action]:
        """检查成交是否超过限制"""
        actions = []
        
        # 获取账户和合约信息
        account_id = trade.account_id if trade.account_id else (order.account_id if order else None)
        contract_id = trade.contract_id if trade.contract_id else (order.contract_id if order else None)
        
        if not account_id or not contract_id:
            return actions
        
        # 根据聚合级别获取目标ID
        target_ids = self._get_target_ids(account_id, contract_id)
        
        for target_id in target_ids:
            # 如果配置了特定目标，检查是否在列表中
            if self.volume_config.target_ids and target_id not in self.volume_config.target_ids:
                continue
            
            # 获取统计值
            if self.volume_config.time_window:
                # 时间窗口统计
                value, count = self.stats_engine.get_window_stat(
                    self.volume_config.metric_type,
                    self.volume_config.aggregation_level,
                    target_id,
                    self.volume_config.time_window
                )
            else:
                # 日统计
                value, count = self.stats_engine.get_daily_stat(
                    self.volume_config.metric_type,
                    self.volume_config.aggregation_level,
                    target_id
                )
            
            # 检查是否超过阈值
            check_value = value
            if self.volume_config.metric_type == MetricType.TRADE_VOLUME:
                check_value = value
            elif self.volume_config.metric_type == MetricType.TRADE_AMOUNT:
                check_value = value
            
            if check_value > self.volume_config.threshold:
                # 生成动作
                for action_type_str in self.volume_config.actions:
                    action_type = ActionType.SUSPEND_ACCOUNT if action_type_str == "suspend_account" else ActionType.WARNING
                    
                    action = Action(
                        action_type=action_type,
                        target_id=target_id,
                        reason=f"{self.volume_config.metric_type.value} exceeded threshold: {check_value:.2f} > {self.volume_config.threshold}",
                        timestamp=trade.timestamp,
                        rule_name=self.volume_config.rule_name,
                        metadata={
                            "metric_type": self.volume_config.metric_type.value,
                            "current_value": check_value,
                            "threshold": self.volume_config.threshold,
                            "aggregation_level": self.volume_config.aggregation_level.value
                        }
                    )
                    actions.append(action)
                    
                    # 记录暂停状态
                    if action_type == ActionType.SUSPEND_ACCOUNT:
                        self.suspend_target(target_id, trade.timestamp)
        
        return actions
    
    def _get_target_ids(self, account_id: str, contract_id: str) -> List[str]:
        """根据聚合级别获取目标ID列表"""
        if self.volume_config.aggregation_level == AggregationLevel.ACCOUNT:
            return [account_id]
        elif self.volume_config.aggregation_level == AggregationLevel.CONTRACT:
            return [contract_id]
        elif self.volume_config.aggregation_level == AggregationLevel.PRODUCT:
            # 从统计引擎获取产品ID
            product_id = self.stats_engine.product_contract_map.get(contract_id, f"UNKNOWN_PRODUCT_{contract_id}")
            return [product_id]
        return []


class FrequencyControlRule(RiskRule):
    """频率控制规则"""
    
    def __init__(self, config: FrequencyControlConfig, stats_engine: StatisticsEngine):
        super().__init__(config, stats_engine)
        self.freq_config = config
        self.auto_resume_check_interval = 1  # 自动恢复检查间隔（秒）
        self.last_auto_resume_check = 0
    
    def check_order(self, order: Order) -> List[Action]:
        """检查订单频率"""
        actions = []
        
        # 根据聚合级别获取目标ID
        target_ids = self._get_target_ids(order.account_id, order.contract_id)
        
        for target_id in target_ids:
            # 如果配置了特定目标，检查是否在列表中
            if self.freq_config.target_ids and target_id not in self.freq_config.target_ids:
                continue
            
            # 检查是否已被暂停
            if self.is_target_suspended(target_id):
                # 如果启用自动恢复，检查是否可以恢复
                if self.freq_config.auto_resume:
                    self._check_auto_resume(target_id, order.timestamp)
                
                # 如果仍被暂停，拦截订单
                if self.is_target_suspended(target_id):
                    action = Action(
                        action_type=ActionType.BLOCK_ORDER,
                        target_id=target_id,
                        reason=f"Order frequency control: target {target_id} is suspended",
                        timestamp=order.timestamp,
                        rule_name=self.freq_config.rule_name,
                        metadata={
                            "order_id": order.oid,
                            "aggregation_level": self.freq_config.aggregation_level.value
                        }
                    )
                    actions.append(action)
                    continue
            
            # 获取当前频率
            value, count = self.stats_engine.get_window_stat(
                MetricType.ORDER_FREQUENCY,
                self.freq_config.aggregation_level,
                target_id,
                self.freq_config.time_window
            )
            
            # 检查是否超过限制
            if count >= self.freq_config.max_count:
                # 生成暂停动作
                for action_type_str in self.freq_config.actions:
                    action_type = ActionType.SUSPEND_ORDER if action_type_str == "suspend_order" else ActionType.WARNING
                    
                    action = Action(
                        action_type=action_type,
                        target_id=target_id,
                        reason=f"Order frequency exceeded: {count} >= {self.freq_config.max_count} in {self.freq_config.time_window}s",
                        timestamp=order.timestamp,
                        rule_name=self.freq_config.rule_name,
                        metadata={
                            "current_count": count,
                            "max_count": self.freq_config.max_count,
                            "time_window": self.freq_config.time_window,
                            "aggregation_level": self.freq_config.aggregation_level.value
                        }
                    )
                    actions.append(action)
                    
                    # 记录暂停状态
                    if action_type == ActionType.SUSPEND_ORDER:
                        self.suspend_target(target_id, order.timestamp)
                
                # 拦截当前订单
                block_action = Action(
                    action_type=ActionType.BLOCK_ORDER,
                    target_id=target_id,
                    reason=f"Order blocked due to frequency limit",
                    timestamp=order.timestamp,
                    rule_name=self.freq_config.rule_name,
                    metadata={"order_id": order.oid}
                )
                actions.append(block_action)
        
        return actions
    
    def check_trade(self, trade: Trade, order: Optional[Order] = None) -> List[Action]:
        """成交检查（频率规则不检查成交）"""
        return []
    
    def _get_target_ids(self, account_id: str, contract_id: str) -> List[str]:
        """根据聚合级别获取目标ID列表"""
        if self.freq_config.aggregation_level == AggregationLevel.ACCOUNT:
            return [account_id]
        elif self.freq_config.aggregation_level == AggregationLevel.CONTRACT:
            return [contract_id]
        elif self.freq_config.aggregation_level == AggregationLevel.PRODUCT:
            product_id = self.stats_engine.product_contract_map.get(contract_id, f"UNKNOWN_PRODUCT_{contract_id}")
            return [product_id]
        return []
    
    def _check_auto_resume(self, target_id: str, current_timestamp: int):
        """检查是否可以自动恢复"""
        current_time_sec = current_timestamp // 1_000_000_000
        
        # 限制检查频率
        if current_time_sec - self.last_auto_resume_check < self.auto_resume_check_interval:
            return
        
        self.last_auto_resume_check = current_time_sec
        
        # 获取当前频率
        value, count = self.stats_engine.get_window_stat(
            MetricType.ORDER_FREQUENCY,
            self.freq_config.aggregation_level,
            target_id,
            self.freq_config.time_window
        )
        
        # 如果频率已降到阈值以下，恢复
        if count < self.freq_config.max_count:
            self.resume_target(target_id)