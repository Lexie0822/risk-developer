"""
风控引擎主模块
"""
from typing import List, Dict, Optional
import logging
from threading import Lock
import time

from .models import Order, Trade, Action
from .config import RiskControlConfig, VolumeControlConfig, FrequencyControlConfig, ProductConfig
from .statistics import StatisticsEngine
from .rules import RiskRule, VolumeControlRule, FrequencyControlRule


class RiskControlEngine:
    """风控引擎"""
    
    def __init__(self, config: Optional[RiskControlConfig] = None):
        """
        初始化风控引擎
        
        Args:
            config: 风控配置，如果为None则使用默认配置
        """
        self.config = config if config else RiskControlConfig()
        self.stats_engine = StatisticsEngine()
        self.rules: List[RiskRule] = []
        self.order_cache: Dict[int, Order] = {}  # oid -> Order 缓存
        self.lock = Lock()
        
        # 设置日志
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=getattr(logging, self.config.global_settings.get("log_level", "INFO")),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # 初始化规则
        self._init_rules()
        
        # 初始化产品-合约映射
        self._init_product_mappings()
        
        self.logger.info("Risk control engine initialized")
    
    def _init_rules(self):
        """根据配置初始化规则"""
        for rule_config in self.config.get_enabled_rules():
            if isinstance(rule_config, VolumeControlConfig):
                rule = VolumeControlRule(rule_config, self.stats_engine)
                self.rules.append(rule)
                self.logger.info(f"Loaded volume control rule: {rule_config.rule_name}")
            elif isinstance(rule_config, FrequencyControlConfig):
                rule = FrequencyControlRule(rule_config, self.stats_engine)
                self.rules.append(rule)
                self.logger.info(f"Loaded frequency control rule: {rule_config.rule_name}")
        
        # 按优先级排序规则
        self.rules.sort(key=lambda r: r.config.priority, reverse=True)
    
    def _init_product_mappings(self):
        """初始化产品-合约映射"""
        for product in self.config.products.values():
            for contract_id in product.contracts:
                self.stats_engine.update_product_contract_mapping(contract_id, product.product_id)
    
    def process_order(self, order: Order) -> List[Action]:
        """
        处理订单事件
        
        Args:
            order: 订单对象
            
        Returns:
            触发的风控动作列表
        """
        if not self.config.global_settings.get("enable_risk_control", True):
            return []
        
        start_time = time.time()
        actions = []
        
        try:
            # 缓存订单
            with self.lock:
                self.order_cache[order.oid] = order
            
            # 更新统计
            self.stats_engine.record_order(order)
            
            # 执行规则检查
            max_rules = self.config.global_settings.get("max_rules_per_event", 100)
            for i, rule in enumerate(self.rules):
                if i >= max_rules:
                    self.logger.warning(f"Max rules limit reached ({max_rules})")
                    break
                
                try:
                    rule_actions = rule.check_order(order)
                    actions.extend(rule_actions)
                except Exception as e:
                    self.logger.error(f"Error in rule {rule.config.rule_name}: {e}")
            
            # 记录性能指标
            elapsed_us = int((time.time() - start_time) * 1_000_000)
            if elapsed_us > 1000:  # 超过1毫秒警告
                self.logger.warning(f"Order processing took {elapsed_us}us")
            
            # 记录触发的动作
            for action in actions:
                self.logger.info(f"Action triggered: {action.action_type.value} for {action.target_id} - {action.reason}")
            
        except Exception as e:
            self.logger.error(f"Error processing order {order.oid}: {e}")
        
        return actions
    
    def process_trade(self, trade: Trade) -> List[Action]:
        """
        处理成交事件
        
        Args:
            trade: 成交对象
            
        Returns:
            触发的风控动作列表
        """
        if not self.config.global_settings.get("enable_risk_control", True):
            return []
        
        start_time = time.time()
        actions = []
        
        try:
            # 查找对应的订单
            order = None
            with self.lock:
                order = self.order_cache.get(trade.oid)
            
            # 如果找到订单，更新trade的冗余字段
            if order:
                trade.account_id = order.account_id
                trade.contract_id = order.contract_id
            
            # 更新统计
            self.stats_engine.record_trade(trade, order)
            
            # 执行规则检查
            max_rules = self.config.global_settings.get("max_rules_per_event", 100)
            for i, rule in enumerate(self.rules):
                if i >= max_rules:
                    self.logger.warning(f"Max rules limit reached ({max_rules})")
                    break
                
                try:
                    rule_actions = rule.check_trade(trade, order)
                    actions.extend(rule_actions)
                except Exception as e:
                    self.logger.error(f"Error in rule {rule.config.rule_name}: {e}")
            
            # 记录性能指标
            elapsed_us = int((time.time() - start_time) * 1_000_000)
            if elapsed_us > 1000:  # 超过1毫秒警告
                self.logger.warning(f"Trade processing took {elapsed_us}us")
            
            # 记录触发的动作
            for action in actions:
                self.logger.info(f"Action triggered: {action.action_type.value} for {action.target_id} - {action.reason}")
            
        except Exception as e:
            self.logger.error(f"Error processing trade {trade.tid}: {e}")
        
        return actions
    
    def add_product(self, product: ProductConfig):
        """动态添加产品配置"""
        self.config.add_product(product)
        for contract_id in product.contracts:
            self.stats_engine.update_product_contract_mapping(contract_id, product.product_id)
    
    def reload_config(self, config: RiskControlConfig):
        """重新加载配置"""
        self.logger.info("Reloading configuration...")
        self.config = config
        self.rules.clear()
        self._init_rules()
        self._init_product_mappings()
        self.logger.info("Configuration reloaded")
    
    def get_statistics(self, target_id: str) -> Dict:
        """获取指定目标的统计信息"""
        return self.stats_engine.get_all_stats_for_target(target_id)
    
    def reset_daily_stats(self):
        """重置日统计（日终处理）"""
        self.logger.info("Resetting daily statistics...")
        self.stats_engine.reset_daily_stats()
        
        # 清理订单缓存（保留最近1小时的订单）
        current_time = time.time() * 1_000_000_000  # 纳秒
        one_hour_ago = current_time - 3600 * 1_000_000_000
        
        with self.lock:
            old_orders = [oid for oid, order in self.order_cache.items() if order.timestamp < one_hour_ago]
            for oid in old_orders:
                del self.order_cache[oid]
        
        self.logger.info(f"Daily reset completed, cleaned {len(old_orders)} old orders")
    
    def get_suspended_targets(self) -> Dict[str, List[str]]:
        """获取所有被暂停的目标"""
        result = {}
        for rule in self.rules:
            with rule.lock:
                if rule.suspended_targets:
                    result[rule.config.rule_name] = list(rule.suspended_targets.keys())
        return result