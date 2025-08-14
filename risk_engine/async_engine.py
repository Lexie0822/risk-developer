"""
异步高性能风控引擎。

设计目标：
- 高并发：支持百万级/秒事件处理
- 低延迟：微秒级响应时间
- 可扩展：支持动态规则配置和热更新
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
import threading
from collections import deque
import weakref

from .models import Order, Trade
from .actions import Action
from .rules import Rule, RuleContext, RuleResult
from .config import RiskEngineConfig, DynamicRuleConfig, RiskEngineRuntimeConfig
from .state import MultiDimDailyCounter, ShardedLockDict
from .dimensions import InstrumentCatalog


@dataclass
class AsyncEngineConfig:
    """异步引擎配置。"""
    max_concurrent_tasks: int = 1000  # 最大并发任务数
    task_timeout_ms: int = 100  # 任务超时时间（毫秒）
    batch_size: int = 1000  # 批处理大小
    num_workers: int = 8  # 工作线程数
    enable_batching: bool = True  # 启用批处理
    enable_async_io: bool = True  # 启用异步IO


class AsyncRiskEngine:
    """异步高性能风控引擎。"""
    
    def __init__(self, 
                 config: RiskEngineConfig,
                 async_config: Optional[AsyncEngineConfig] = None,
                 action_sink: Optional[Callable[[Action, str, Any], None]] = None):
        """初始化异步风控引擎。"""
        self.config = config
        self.async_config = async_config or AsyncEngineConfig()
        self.action_sink = action_sink or self._default_action_sink
        
        # 核心组件
        self._catalog = InstrumentCatalog(
            contract_to_product=config.contract_to_product,
            contract_to_exchange=config.contract_to_exchange,
        )
        self._daily_counter = MultiDimDailyCounter(ShardedLockDict(config.num_shards))
        self._order_rate_windows: Dict[str, Any] = {}
        
        # 异步处理
        self._order_queue: asyncio.Queue = asyncio.Queue(maxsize=config.max_queue_size)
        self._trade_queue: asyncio.Queue = asyncio.Queue(maxsize=config.max_queue_size)
        self._action_queue: asyncio.Queue = asyncio.Queue(maxsize=config.max_queue_size)
        
        # 规则管理
        self._rules: List[Rule] = []
        self._runtime_config = RiskEngineRuntimeConfig()
        self._rules_lock = threading.RLock()
        
        # 性能监控
        self._stats = {
            'orders_processed': 0,
            'trades_processed': 0,
            'actions_generated': 0,
            'avg_latency_ns': 0,
            'max_latency_ns': 0,
            'throughput_ops_per_sec': 0,
        }
        self._stats_lock = threading.Lock()
        
        # 工作线程池
        self._executor = ThreadPoolExecutor(max_workers=config.worker_threads)
        
        # 运行状态
        self._running = False
        self._tasks: List[asyncio.Task] = []
    
    async def start(self):
        """启动异步引擎。"""
        if self._running:
            return
        
        self._running = True
        
        # 启动工作协程
        self._tasks = [
            asyncio.create_task(self._order_processor()),
            asyncio.create_task(self._trade_processor()),
            asyncio.create_task(self._action_processor()),
            asyncio.create_task(self._metrics_collector()),
        ]
        
        # 启动批处理协程（如果启用）
        if self.async_config.enable_batching:
            self._tasks.append(asyncio.create_task(self._batch_processor()))
        
        print("异步风控引擎已启动")
    
    async def stop(self):
        """停止异步引擎。"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消所有任务
        for task in self._tasks:
            task.cancel()
        
        # 等待任务完成
        await asyncio.gather(*self._tasks, return_exceptions=True)
        
        # 关闭线程池
        self._executor.shutdown(wait=True)
        
        print("异步风控引擎已停止")
    
    async def submit_order(self, order: Order):
        """提交订单到处理队列。"""
        await self._order_queue.put(order)
    
    async def submit_trade(self, trade: Trade):
        """提交成交到处理队列。"""
        await self._trade_queue.put(trade)
    
    async def _order_processor(self):
        """订单处理协程。"""
        while self._running:
            try:
                # 批量获取订单
                orders = []
                try:
                    # 非阻塞获取第一个订单
                    order = await asyncio.wait_for(
                        self._order_queue.get(), 
                        timeout=0.001
                    )
                    orders.append(order)
                    
                    # 尝试获取更多订单进行批处理
                    while len(orders) < self.async_config.batch_size:
                        try:
                            order = self._order_queue.get_nowait()
                            orders.append(order)
                        except asyncio.QueueEmpty:
                            break
                except asyncio.TimeoutError:
                    continue
                
                # 批量处理订单
                await self._process_orders_batch(orders)
                
            except Exception as e:
                print(f"订单处理错误: {e}")
                await asyncio.sleep(0.001)
    
    async def _trade_processor(self):
        """成交处理协程。"""
        while self._running:
            try:
                # 批量获取成交
                trades = []
                try:
                    trade = await asyncio.wait_for(
                        self._trade_queue.get(), 
                        timeout=0.001
                    )
                    trades.append(trade)
                    
                    while len(trades) < self.async_config.batch_size:
                        try:
                            trade = self._trade_queue.get_nowait()
                            trades.append(trade)
                        except asyncio.QueueEmpty:
                            break
                except asyncio.TimeoutError:
                    continue
                
                # 批量处理成交
                await self._process_trades_batch(trades)
                
            except Exception as e:
                print(f"成交处理错误: {e}")
                await asyncio.sleep(0.001)
    
    async def _process_orders_batch(self, orders: List[Order]):
        """批量处理订单。"""
        start_time = time.perf_counter_ns()
        
        # 在线程池中执行规则评估（避免阻塞事件循环）
        loop = asyncio.get_event_loop()
        tasks = []
        
        for order in orders:
            task = loop.run_in_executor(
                self._executor, 
                self._evaluate_order_rules, 
                order
            )
            tasks.append(task)
        
        # 等待所有规则评估完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理结果
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"订单 {orders[i].oid} 规则评估错误: {result}")
                continue
            
            if result and result.actions:
                await self._action_queue.put((result.actions, result.reasons, orders[i]))
        
        # 更新统计
        end_time = time.perf_counter_ns()
        latency = end_time - start_time
        
        with self._stats_lock:
            self._stats['orders_processed'] += len(orders)
            self._stats['avg_latency_ns'] = (
                self._stats['avg_latency_ns'] * 0.95 + latency * 0.05
            )
            self._stats['max_latency_ns'] = max(
                self._stats['max_latency_ns'], 
                latency
            )
    
    async def _process_trades_batch(self, trades: List[Trade]):
        """批量处理成交。"""
        start_time = time.perf_counter_ns()
        
        loop = asyncio.get_event_loop()
        tasks = []
        
        for trade in trades:
            task = loop.run_in_executor(
                self._executor, 
                self._evaluate_trade_rules, 
                trade
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"成交 {trades[i].tid} 规则评估错误: {result}")
                continue
            
            if result and result.actions:
                await self._action_queue.put((result.actions, result.reasons, trades[i]))
        
        # 更新统计
        end_time = time.perf_counter_ns()
        latency = end_time - start_time
        
        with self._stats_lock:
            self._stats['trades_processed'] += len(trades)
            self._stats['avg_latency_ns'] = (
                self._stats['avg_latency_ns'] * 0.95 + latency * 0.05
            )
            self._stats['max_latency_ns'] = max(
                self._stats['max_latency_ns'], 
                latency
            )
    
    def _evaluate_order_rules(self, order: Order) -> Optional[RuleResult]:
        """在线程池中评估订单规则。"""
        with self._rules_lock:
            rules = self._rules.copy()
        
        ctx = RuleContext(
            catalog=self._catalog,
            daily_counter=self._daily_counter,
            order_rate_windows=self._order_rate_windows,
        )
        
        for rule in rules:
            try:
                result = rule.on_order(ctx, order)
                if result and result.actions:
                    return result
            except Exception as e:
                print(f"规则 {rule.rule_id} 评估错误: {e}")
        
        return None
    
    def _evaluate_trade_rules(self, trade: Trade) -> Optional[RuleResult]:
        """在线程池中评估成交规则。"""
        with self._rules_lock:
            rules = self._rules.copy()
        
        ctx = RuleContext(
            catalog=self._catalog,
            daily_counter=self._daily_counter,
            order_rate_windows=self._order_rate_windows,
        )
        
        for rule in rules:
            try:
                result = rule.on_trade(ctx, trade)
                if result and result.actions:
                    return result
            except Exception as e:
                print(f"规则 {rule.rule_id} 评估错误: {e}")
        
        return None
    
    async def _action_processor(self):
        """动作处理协程。"""
        while self._running:
            try:
                actions, reasons, obj = await self._action_queue.get()
                
                for action in actions:
                    await self._execute_action(action, reasons, obj)
                
                with self._stats_lock:
                    self._stats['actions_generated'] += len(actions)
                
            except Exception as e:
                print(f"动作处理错误: {e}")
                await asyncio.sleep(0.001)
    
    async def _execute_action(self, action: Action, reasons: List[str], obj: Any):
        """执行风控动作。"""
        try:
            # 在线程池中执行动作（避免阻塞事件循环）
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                self.action_sink,
                action,
                f"RULE-{id(action)}",
                obj
            )
        except Exception as e:
            print(f"执行动作 {action} 错误: {e}")
    
    async def _batch_processor(self):
        """批处理协程。"""
        while self._running:
            try:
                # 定期执行批处理任务
                await asyncio.sleep(0.1)
                
                # 这里可以添加批量清理、统计等任务
                
            except Exception as e:
                print(f"批处理错误: {e}")
                await asyncio.sleep(0.001)
    
    async def _metrics_collector(self):
        """指标收集协程。"""
        while self._running:
            try:
                await asyncio.sleep(1)  # 每秒收集一次
                
                # 计算吞吐量
                with self._stats_lock:
                    total_ops = (
                        self._stats['orders_processed'] + 
                        self._stats['trades_processed']
                    )
                    self._stats['throughput_ops_per_sec'] = total_ops
                
                # 输出性能指标
                if self.config.enable_metrics:
                    print(f"性能指标: {self._stats}")
                
            except Exception as e:
                print(f"指标收集错误: {e}")
    
    def add_rule(self, rule: Rule):
        """添加规则。"""
        with self._rules_lock:
            self._rules.append(rule)
    
    def remove_rule(self, rule_id: str):
        """移除规则。"""
        with self._rules_lock:
            self._rules = [r for r in self._rules if getattr(r, 'rule_id', None) != rule_id]
    
    def get_stats(self) -> Dict:
        """获取性能统计。"""
        with self._stats_lock:
            return self._stats.copy()
    
    def _default_action_sink(self, action: Action, rule_id: str, obj: Any):
        """默认动作处理器。"""
        print(f"风控动作: {action.name} from {rule_id} for {obj}")


# 便捷构造函数
def create_async_engine(config: RiskEngineConfig) -> AsyncRiskEngine:
    """创建异步风控引擎。"""
    from .rules import AccountTradeMetricLimitRule, OrderRateLimitRule
    from .metrics import MetricType
    
    engine = AsyncRiskEngine(config)
    
    # 添加默认规则
    if config.volume_limit:
        engine.add_rule(AccountTradeMetricLimitRule(
            rule_id="VOLUME-LIMIT",
            metric=config.volume_limit.metric,
            threshold=config.volume_limit.threshold,
            actions=(Action.SUSPEND_ACCOUNT_TRADING,),
            by_account=True,
            by_product=config.volume_limit.dimension.value == "product",
            by_contract=config.volume_limit.dimension.value == "contract",
        ))
    
    if config.order_rate_limit:
        engine.add_rule(OrderRateLimitRule(
            rule_id="ORDER-RATE-LIMIT",
            threshold=config.order_rate_limit.threshold,
            window_seconds=max(1, config.order_rate_limit.get_window_ns() // 1_000_000_000),
            suspend_actions=(Action.SUSPEND_ORDERING,),
            resume_actions=(Action.RESUME_ORDERING,),
            dimension=config.order_rate_limit.dimension.value,
        ))
    
    return engine