"""
Main risk control engine implementation.
"""

import threading
import queue
import time
from typing import List, Dict, Optional, Callable, Set
from collections import defaultdict
from dataclasses import dataclass, field
import logging

from .models import Order, Trade, Action, ActionType, RiskEvent
from .metrics import MetricsCollector, TimeWindow
from .rules import RuleManager, RuleContext, RuleResult
from .config import ConfigManager, RiskControlConfig


logger = logging.getLogger(__name__)


@dataclass
class EngineStats:
    """Statistics for the risk control engine"""
    orders_processed: int = 0
    trades_processed: int = 0
    actions_generated: int = 0
    rule_evaluations: int = 0
    avg_latency_ns: float = 0
    max_latency_ns: int = 0
    start_time: int = field(default_factory=lambda: int(time.time() * 1e9))
    
    def update_latency(self, latency_ns: int):
        """Update latency statistics"""
        self.max_latency_ns = max(self.max_latency_ns, latency_ns)
        # Simple moving average
        self.avg_latency_ns = (self.avg_latency_ns * 0.95 + latency_ns * 0.05)
    
    def get_throughput(self) -> float:
        """Get throughput in operations per second"""
        elapsed_ns = int(time.time() * 1e9) - self.start_time
        if elapsed_ns > 0:
            total_ops = self.orders_processed + self.trades_processed
            return total_ops * 1e9 / elapsed_ns
        return 0.0


class RiskControlEngine:
    """
    Main risk control engine for processing orders and trades.
    
    Features:
    - High-performance order and trade processing
    - Multi-threaded architecture for scalability
    - Real-time metric collection and rule evaluation
    - Configurable rules with hot-reloading support
    - Comprehensive monitoring and statistics
    """
    
    def __init__(self, config: Optional[RiskControlConfig] = None, 
                 num_workers: int = 4):
        """
        Initialize the risk control engine.
        
        Args:
            config: Initial configuration (optional)
            num_workers: Number of worker threads for processing
        """
        # Core components
        self.metrics_collector = MetricsCollector()
        self.rule_manager = RuleManager(self.metrics_collector)
        self.config_manager = ConfigManager()
        
        # Load configuration
        if config:
            self.config_manager.config = config
            self.rule_manager.load_from_config(config)
        else:
            # Load default configuration
            default_config = self.config_manager.create_default_config()
            self.config_manager.config = default_config
            self.rule_manager.load_from_config(default_config)
        
        # Processing queues
        self.order_queue: queue.Queue = queue.Queue(maxsize=10000)
        self.trade_queue: queue.Queue = queue.Queue(maxsize=10000)
        
        # Action handlers
        self.action_handlers: Dict[ActionType, List[Callable]] = defaultdict(list)
        self.event_handlers: List[Callable] = []
        
        # State management
        self.suspended_accounts: Set[str] = set()
        self.suspended_order_accounts: Set[str] = set()
        self._lock = threading.RLock()
        
        # Statistics
        self.stats = EngineStats()
        
        # Worker threads
        self.num_workers = num_workers
        self.workers = []
        self.running = False
        
        # Order cache for trade processing
        self.order_cache: Dict[int, Order] = {}
        self.cache_lock = threading.RLock()
        
        # Register configuration watcher
        self.config_manager.add_watcher(self._on_config_change)
    
    def start(self):
        """Start the risk control engine"""
        if self.running:
            return
        
        self.running = True
        
        # Start worker threads
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"RiskControlWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
        
        # Start metric cleanup thread
        cleanup_thread = threading.Thread(
            target=self._metric_cleanup_loop,
            name="MetricCleanup",
            daemon=True
        )
        cleanup_thread.start()
        self.workers.append(cleanup_thread)
        
        logger.info(f"Risk control engine started with {self.num_workers} workers")
    
    def stop(self):
        """Stop the risk control engine"""
        self.running = False
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5.0)
        
        self.workers.clear()
        logger.info("Risk control engine stopped")
    
    def process_order(self, order: Order) -> List[Action]:
        """
        Process an order through the risk control system.
        
        Args:
            order: Order to process
            
        Returns:
            List of actions generated
        """
        start_time = int(time.time() * 1e9)
        
        # Record order metrics
        self.metrics_collector.record_order(order)
        
        # Cache order for trade processing
        with self.cache_lock:
            self.order_cache[order.oid] = order
            # Limit cache size
            if len(self.order_cache) > 100000:
                # Remove oldest entries
                oldest_oids = sorted(self.order_cache.keys())[:10000]
                for oid in oldest_oids:
                    self.order_cache.pop(oid, None)
        
        # Pre-trade checks
        actions = []
        
        # Check if account is suspended
        with self._lock:
            if order.account_id in self.suspended_accounts:
                action = Action(
                    action_type=ActionType.SUSPEND_ACCOUNT,
                    account_id=order.account_id,
                    reason="Account is suspended",
                    metadata={"order_id": order.oid}
                )
                actions.append(action)
                self._handle_action(action)
                return actions
            
            if order.account_id in self.suspended_order_accounts:
                action = Action(
                    action_type=ActionType.SUSPEND_ORDER,
                    account_id=order.account_id,
                    reason="Order submission is suspended for this account",
                    metadata={"order_id": order.oid}
                )
                actions.append(action)
                self._handle_action(action)
                return actions
        
        # Evaluate rules
        context = RuleContext(order=order)
        rule_results = self.rule_manager.evaluate_all(context)
        
        # Process rule results
        for result in rule_results:
            if result.triggered:
                actions.extend(result.actions)
                for event in result.events:
                    self._handle_event(event)
        
        # Handle actions
        for action in actions:
            self._handle_action(action)
        
        # Update statistics
        latency_ns = int(time.time() * 1e9) - start_time
        self.stats.orders_processed += 1
        self.stats.actions_generated += len(actions)
        self.stats.rule_evaluations += len(rule_results)
        self.stats.update_latency(latency_ns)
        
        return actions
    
    def process_trade(self, trade: Trade) -> List[Action]:
        """
        Process a trade through the risk control system.
        
        Args:
            trade: Trade to process
            
        Returns:
            List of actions generated
        """
        start_time = int(time.time() * 1e9)
        
        # Get associated order
        order = None
        with self.cache_lock:
            order = self.order_cache.get(trade.oid)
        
        if order:
            # Enrich trade with order information
            trade.account_id = order.account_id
            trade.contract_id = order.contract_id
            
            # Record trade metrics
            self.metrics_collector.record_trade(trade, order)
            
            # Post-trade checks
            context = RuleContext(order=order, trade=trade)
            rule_results = self.rule_manager.evaluate_all(context)
            
            # Process rule results
            actions = []
            for result in rule_results:
                if result.triggered:
                    actions.extend(result.actions)
                    for event in result.events:
                        self._handle_event(event)
            
            # Handle actions
            for action in actions:
                self._handle_action(action)
            
            # Update statistics
            latency_ns = int(time.time() * 1e9) - start_time
            self.stats.trades_processed += 1
            self.stats.actions_generated += len(actions)
            self.stats.rule_evaluations += len(rule_results)
            self.stats.update_latency(latency_ns)
            
            return actions
        else:
            logger.warning(f"Trade {trade.tid} has no associated order {trade.oid}")
            self.stats.trades_processed += 1
            return []
    
    def process_order_async(self, order: Order):
        """Process order asynchronously"""
        try:
            self.order_queue.put_nowait(order)
        except queue.Full:
            logger.error("Order queue is full, dropping order")
    
    def process_trade_async(self, trade: Trade):
        """Process trade asynchronously"""
        try:
            self.trade_queue.put_nowait(trade)
        except queue.Full:
            logger.error("Trade queue is full, dropping trade")
    
    def register_action_handler(self, action_type: ActionType, handler: Callable):
        """Register a handler for specific action types"""
        self.action_handlers[action_type].append(handler)
    
    def register_event_handler(self, handler: Callable):
        """Register a handler for risk events"""
        self.event_handlers.append(handler)
    
    def get_statistics(self) -> Dict:
        """Get engine statistics"""
        return {
            "engine": {
                "orders_processed": self.stats.orders_processed,
                "trades_processed": self.stats.trades_processed,
                "actions_generated": self.stats.actions_generated,
                "rule_evaluations": self.stats.rule_evaluations,
                "avg_latency_us": self.stats.avg_latency_ns / 1000,
                "max_latency_us": self.stats.max_latency_ns / 1000,
                "throughput_ops_per_sec": self.stats.get_throughput()
            },
            "rules": self.rule_manager.get_statistics(),
            "state": {
                "suspended_accounts": len(self.suspended_accounts),
                "suspended_order_accounts": len(self.suspended_order_accounts),
                "order_cache_size": len(self.order_cache)
            }
        }
    
    def get_account_metrics(self, account_id: str) -> Dict:
        """Get metrics for a specific account"""
        current_time = int(time.time() * 1e9)
        
        return {
            "daily_volume": self.metrics_collector.get_account_volume(
                account_id, TimeWindow.days(1), current_time
            ),
            "hourly_volume": self.metrics_collector.get_account_volume(
                account_id, TimeWindow.hours(1), current_time
            ),
            "order_rate_per_sec": self.metrics_collector.get_account_order_rate(
                account_id, TimeWindow.seconds(1), current_time
            ),
            "order_rate_per_min": self.metrics_collector.get_account_order_rate(
                account_id, TimeWindow.minutes(1), current_time
            )
        }
    
    def update_config(self, config: RiskControlConfig):
        """Update engine configuration"""
        self.config_manager.config = config
        self.rule_manager.load_from_config(config)
    
    def _worker_loop(self):
        """Worker thread main loop"""
        while self.running:
            try:
                # Process orders
                try:
                    order = self.order_queue.get(timeout=0.1)
                    self.process_order(order)
                except queue.Empty:
                    pass
                
                # Process trades
                try:
                    trade = self.trade_queue.get(timeout=0.1)
                    self.process_trade(trade)
                except queue.Empty:
                    pass
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}", exc_info=True)
    
    def _metric_cleanup_loop(self):
        """Periodically clean up expired metrics"""
        while self.running:
            try:
                time.sleep(60)  # Clean up every minute
                current_time = int(time.time() * 1e9)
                self.metrics_collector.engine.clear_expired(current_time)
            except Exception as e:
                logger.error(f"Error in metric cleanup: {e}", exc_info=True)
    
    def _handle_action(self, action: Action):
        """Handle a risk control action"""
        # Update internal state
        with self._lock:
            if action.action_type == ActionType.SUSPEND_ACCOUNT:
                self.suspended_accounts.add(action.account_id)
            elif action.action_type == ActionType.SUSPEND_ORDER:
                self.suspended_order_accounts.add(action.account_id)
            elif action.action_type == ActionType.RESUME_ACCOUNT:
                self.suspended_accounts.discard(action.account_id)
            elif action.action_type == ActionType.RESUME_ORDER:
                self.suspended_order_accounts.discard(action.account_id)
        
        # Call registered handlers
        for handler in self.action_handlers[action.action_type]:
            try:
                handler(action)
            except Exception as e:
                logger.error(f"Error in action handler: {e}", exc_info=True)
    
    def _handle_event(self, event: RiskEvent):
        """Handle a risk event"""
        for handler in self.event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}", exc_info=True)
    
    def _on_config_change(self, config: RiskControlConfig):
        """Handle configuration change"""
        logger.info("Configuration changed, reloading rules")
        self.rule_manager.load_from_config(config)