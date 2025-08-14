from typing import List, Dict, Optional, Callable
import time
import threading
from queue import Queue, Empty
from models import Order, Trade, Action, ActionType, get_current_timestamp_ns
from statistics_engine import MultiDimensionalStatistics
from rule_engine import RiskRuleEngine
from config_manager import RiskConfigManager


class RiskControlEngine:
    """金融风控引擎主类"""
    
    def __init__(self, config_file: Optional[str] = None):
        # 初始化各个组件
        self.statistics_engine = MultiDimensionalStatistics()
        self.rule_engine = RiskRuleEngine()
        self.config_manager = RiskConfigManager(config_file)
        
        # 数据处理队列
        self.order_queue = Queue()
        self.trade_queue = Queue()
        self.action_queue = Queue()
        
        # 账户状态管理
        self.account_status = {}  # 账户状态：normal, suspended_trading, suspended_order
        self.contract_status = {}  # 合约状态
        
        # 回调函数
        self.action_callbacks: List[Callable[[Action], None]] = []
        
        # 线程控制
        self.running = False
        self.processing_threads = []
        
        # 性能统计
        self.performance_stats = {
            "total_orders_processed": 0,
            "total_trades_processed": 0,
            "total_actions_generated": 0,
            "average_processing_time_ns": 0,
            "max_processing_time_ns": 0
        }
        
        # 锁
        self.status_lock = threading.RLock()
        
    def initialize(self) -> bool:
        """初始化引擎"""
        try:
            # 加载配置
            if not self.config_manager.load_config():
                print("配置加载失败")
                return False
                
            # 验证配置
            errors = self.config_manager.validate_config()
            if errors:
                print(f"配置验证失败: {errors}")
                return False
                
            # 加载规则到规则引擎
            for rule in self.config_manager.get_all_rules():
                if not self.rule_engine.add_rule(rule):
                    print(f"加载规则失败: {rule.rule_id}")
                    return False
                    
            print(f"成功加载 {len(self.config_manager.get_all_rules())} 个风控规则")
            return True
            
        except Exception as e:
            print(f"引擎初始化失败: {e}")
            return False
            
    def start(self) -> bool:
        """启动引擎"""
        if self.running:
            print("引擎已在运行")
            return False
            
        if not self.initialize():
            return False
            
        self.running = True
        
        # 启动处理线程
        self._start_processing_threads()
        
        print("风控引擎启动成功")
        return True
        
    def stop(self):
        """停止引擎"""
        if not self.running:
            return
            
        self.running = False
        
        # 等待处理线程结束
        for thread in self.processing_threads:
            thread.join(timeout=1.0)
            
        self.processing_threads.clear()
        print("风控引擎已停止")
        
    def _start_processing_threads(self):
        """启动处理线程"""
        # 订单处理线程
        order_thread = threading.Thread(target=self._process_orders, daemon=True)
        order_thread.start()
        self.processing_threads.append(order_thread)
        
        # 成交处理线程
        trade_thread = threading.Thread(target=self._process_trades, daemon=True)
        trade_thread.start()
        self.processing_threads.append(trade_thread)
        
        # 动作执行线程
        action_thread = threading.Thread(target=self._process_actions, daemon=True)
        action_thread.start()
        self.processing_threads.append(action_thread)
        
    def _process_orders(self):
        """处理订单队列"""
        while self.running:
            try:
                order = self.order_queue.get(timeout=0.1)
                start_time = time.perf_counter_ns()
                
                # 检查账户状态
                if not self._check_account_order_permission(order):
                    action = Action(
                        action_type=ActionType.REJECT_ORDER,
                        target_id=order.account_id,
                        reason=f"账户 {order.account_id} 已被暂停报单",
                        timestamp=get_current_timestamp_ns()
                    )
                    self.action_queue.put(action)
                    continue
                    
                # 更新订单统计
                self.statistics_engine.update_order_statistics(order)
                
                # 检查规则（仅订单相关规则）
                actions = self.rule_engine.check_all_rules(order, None, self.statistics_engine)
                for action in actions:
                    self.action_queue.put(action)
                    
                # 更新性能统计
                processing_time = time.perf_counter_ns() - start_time
                self._update_performance_stats("order", processing_time)
                
            except Empty:
                continue
            except Exception as e:
                print(f"处理订单时发生错误: {e}")
                
    def _process_trades(self):
        """处理成交队列"""
        orders_cache = {}  # 简单的订单缓存
        
        while self.running:
            try:
                trade_data = self.trade_queue.get(timeout=0.1)
                trade = trade_data['trade']
                order = trade_data['order']
                
                start_time = time.perf_counter_ns()
                
                # 更新成交统计
                self.statistics_engine.update_trade_statistics(trade, order)
                
                # 检查所有规则
                actions = self.rule_engine.check_all_rules(order, trade, self.statistics_engine)
                for action in actions:
                    self.action_queue.put(action)
                    
                # 更新性能统计
                processing_time = time.perf_counter_ns() - start_time
                self._update_performance_stats("trade", processing_time)
                
            except Empty:
                continue
            except Exception as e:
                print(f"处理成交时发生错误: {e}")
                
    def _process_actions(self):
        """处理动作队列"""
        while self.running:
            try:
                action = self.action_queue.get(timeout=0.1)
                start_time = time.perf_counter_ns()
                
                # 执行动作
                self._execute_action(action)
                
                # 调用回调函数
                for callback in self.action_callbacks:
                    try:
                        callback(action)
                    except Exception as e:
                        print(f"动作回调执行失败: {e}")
                        
                # 更新性能统计
                processing_time = time.perf_counter_ns() - start_time
                self._update_performance_stats("action", processing_time)
                
            except Empty:
                continue
            except Exception as e:
                print(f"处理动作时发生错误: {e}")
                
    def _execute_action(self, action: Action):
        """执行风控动作"""
        with self.status_lock:
            if action.action_type == ActionType.SUSPEND_TRADING:
                self.account_status[action.target_id] = "suspended_trading"
                print(f"暂停账户 {action.target_id} 交易: {action.reason}")
                
            elif action.action_type == ActionType.SUSPEND_ORDER:
                self.account_status[action.target_id] = "suspended_order"
                print(f"暂停账户 {action.target_id} 报单: {action.reason}")
                
            elif action.action_type == ActionType.RESUME_TRADING:
                if action.target_id in self.account_status:
                    del self.account_status[action.target_id]
                print(f"恢复账户 {action.target_id} 交易")
                
            elif action.action_type == ActionType.RESUME_ORDER:
                if action.target_id in self.account_status:
                    del self.account_status[action.target_id]
                print(f"恢复账户 {action.target_id} 报单")
                
            elif action.action_type == ActionType.ALERT:
                print(f"风控告警: {action.reason}")
                
            elif action.action_type == ActionType.REJECT_ORDER:
                print(f"拒绝订单: {action.reason}")
                
        self.performance_stats["total_actions_generated"] += 1
        
    def _check_account_order_permission(self, order: Order) -> bool:
        """检查账户是否允许报单"""
        with self.status_lock:
            status = self.account_status.get(order.account_id, "normal")
            return status not in ["suspended_trading", "suspended_order"]
            
    def _update_performance_stats(self, operation: str, processing_time_ns: int):
        """更新性能统计"""
        if operation == "order":
            self.performance_stats["total_orders_processed"] += 1
        elif operation == "trade":
            self.performance_stats["total_trades_processed"] += 1
            
        # 更新平均处理时间
        total_ops = (self.performance_stats["total_orders_processed"] + 
                    self.performance_stats["total_trades_processed"])
        if total_ops > 0:
            current_avg = self.performance_stats["average_processing_time_ns"]
            self.performance_stats["average_processing_time_ns"] = (
                (current_avg * (total_ops - 1) + processing_time_ns) / total_ops
            )
            
        # 更新最大处理时间
        if processing_time_ns > self.performance_stats["max_processing_time_ns"]:
            self.performance_stats["max_processing_time_ns"] = processing_time_ns
            
    # 公共接口
    def submit_order(self, order: Order):
        """提交订单"""
        if not self.running:
            raise RuntimeError("引擎未运行")
        self.order_queue.put(order)
        
    def submit_trade(self, trade: Trade, order: Order):
        """提交成交"""
        if not self.running:
            raise RuntimeError("引擎未运行")
        self.trade_queue.put({"trade": trade, "order": order})
        
    def add_action_callback(self, callback: Callable[[Action], None]):
        """添加动作回调函数"""
        self.action_callbacks.append(callback)
        
    def remove_action_callback(self, callback: Callable[[Action], None]):
        """移除动作回调函数"""
        if callback in self.action_callbacks:
            self.action_callbacks.remove(callback)
            
    def get_account_status(self, account_id: str) -> str:
        """获取账户状态"""
        with self.status_lock:
            return self.account_status.get(account_id, "normal")
            
    def get_statistics_summary(self) -> Dict:
        """获取统计摘要"""
        current_time = get_current_timestamp_ns()
        stats_summary = self.statistics_engine.get_statistics_summary(current_time)
        stats_summary["performance"] = self.performance_stats.copy()
        stats_summary["rule_status"] = self.rule_engine.get_rule_status()
        return stats_summary
        
    def reload_config(self) -> bool:
        """重新加载配置"""
        if not self.config_manager.reload_config():
            return False
            
        # 重新加载规则
        self.rule_engine = RiskRuleEngine()
        for rule in self.config_manager.get_all_rules():
            self.rule_engine.add_rule(rule)
            
        print("配置重新加载完成")
        return True
        
    def manually_suspend_account(self, account_id: str, reason: str = "手动暂停"):
        """手动暂停账户"""
        action = Action(
            action_type=ActionType.SUSPEND_TRADING,
            target_id=account_id,
            reason=reason,
            timestamp=get_current_timestamp_ns()
        )
        self.action_queue.put(action)
        
    def manually_resume_account(self, account_id: str, reason: str = "手动恢复"):
        """手动恢复账户"""
        action = Action(
            action_type=ActionType.RESUME_TRADING,
            target_id=account_id,
            reason=reason,
            timestamp=get_current_timestamp_ns()
        )
        self.action_queue.put(action)