"""
多维统计引擎
"""
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, deque
from dataclasses import dataclass, field
import time
from threading import Lock
from .models import Order, Trade
from .config import AggregationLevel, MetricType


@dataclass
class StatisticValue:
    """统计值"""
    value: float = 0.0
    count: int = 0
    last_update: int = 0  # 最后更新时间戳
    
    def add(self, amount: float, timestamp: int):
        """添加统计值"""
        self.value += amount
        self.count += 1
        self.last_update = timestamp


@dataclass
class TimeWindowStat:
    """时间窗口统计"""
    window_size: int  # 窗口大小（秒）
    events: deque = field(default_factory=deque)  # (timestamp, value)的队列
    total_value: float = 0.0
    total_count: int = 0
    
    def add_event(self, timestamp: int, value: float = 1.0):
        """添加事件"""
        # 转换为秒级时间戳
        timestamp_sec = timestamp // 1_000_000_000
        
        # 清理过期事件
        current_time = timestamp_sec
        while self.events and self.events[0][0] < current_time - self.window_size:
            old_ts, old_val = self.events.popleft()
            self.total_value -= old_val
            self.total_count -= 1
        
        # 添加新事件
        self.events.append((timestamp_sec, value))
        self.total_value += value
        self.total_count += 1
    
    def get_count(self) -> int:
        """获取当前窗口内的事件数量"""
        return self.total_count
    
    def get_value(self) -> float:
        """获取当前窗口内的总值"""
        return self.total_value


class StatisticsEngine:
    """多维统计引擎"""
    
    def __init__(self):
        # 多级索引的统计数据存储
        # 结构: {metric_type: {aggregation_level: {target_id: StatisticValue}}}
        self.daily_stats: Dict[MetricType, Dict[AggregationLevel, Dict[str, StatisticValue]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(StatisticValue))
        )
        
        # 时间窗口统计
        # 结构: {metric_type: {aggregation_level: {target_id: {window_size: TimeWindowStat}}}}
        self.window_stats: Dict[MetricType, Dict[AggregationLevel, Dict[str, Dict[int, TimeWindowStat]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(TimeWindowStat)))
        )
        
        # 产品-合约映射缓存
        self.product_contract_map: Dict[str, str] = {}
        
        # 线程锁
        self.lock = Lock()
    
    def update_product_contract_mapping(self, contract_id: str, product_id: str):
        """更新产品-合约映射"""
        self.product_contract_map[contract_id] = product_id
    
    def _get_aggregation_keys(self, 
                            account_id: str, 
                            contract_id: str,
                            aggregation_level: AggregationLevel) -> List[str]:
        """根据聚合级别获取聚合键"""
        if aggregation_level == AggregationLevel.ACCOUNT:
            return [account_id]
        elif aggregation_level == AggregationLevel.CONTRACT:
            return [contract_id]
        elif aggregation_level == AggregationLevel.PRODUCT:
            product_id = self.product_contract_map.get(contract_id, f"UNKNOWN_PRODUCT_{contract_id}")
            return [product_id]
        elif aggregation_level == AggregationLevel.ACCOUNT_GROUP:
            # 简化处理：账户组用账户ID前缀
            group_id = account_id.split('_')[0] if '_' in account_id else "DEFAULT_GROUP"
            return [group_id]
        else:
            return []
    
    def record_order(self, order: Order):
        """记录订单统计"""
        with self.lock:
            timestamp = order.timestamp
            
            # 订单量统计
            for level in AggregationLevel:
                keys = self._get_aggregation_keys(order.account_id, order.contract_id, level)
                for key in keys:
                    # 日统计
                    self.daily_stats[MetricType.ORDER_COUNT][level][key].add(1, timestamp)
                    
                    # 时间窗口统计（1秒、60秒）
                    for window_size in [1, 60]:
                        if window_size not in self.window_stats[MetricType.ORDER_FREQUENCY][level][key]:
                            self.window_stats[MetricType.ORDER_FREQUENCY][level][key][window_size] = TimeWindowStat(window_size)
                        self.window_stats[MetricType.ORDER_FREQUENCY][level][key][window_size].add_event(timestamp)
    
    def record_trade(self, trade: Trade, order: Optional[Order] = None):
        """记录成交统计"""
        with self.lock:
            timestamp = trade.timestamp
            
            # 如果没有提供订单信息，使用trade中的冗余字段
            account_id = trade.account_id if trade.account_id else (order.account_id if order else "UNKNOWN")
            contract_id = trade.contract_id if trade.contract_id else (order.contract_id if order else "UNKNOWN")
            
            # 成交量和成交金额统计
            trade_amount = trade.price * trade.volume
            
            for level in AggregationLevel:
                keys = self._get_aggregation_keys(account_id, contract_id, level)
                for key in keys:
                    # 成交量
                    self.daily_stats[MetricType.TRADE_VOLUME][level][key].add(trade.volume, timestamp)
                    # 成交金额
                    self.daily_stats[MetricType.TRADE_AMOUNT][level][key].add(trade_amount, timestamp)
    
    def get_daily_stat(self, 
                      metric_type: MetricType,
                      aggregation_level: AggregationLevel,
                      target_id: str) -> Tuple[float, int]:
        """获取日统计数据"""
        with self.lock:
            stat = self.daily_stats[metric_type][aggregation_level][target_id]
            return stat.value, stat.count
    
    def get_window_stat(self,
                       metric_type: MetricType,
                       aggregation_level: AggregationLevel,
                       target_id: str,
                       window_size: int) -> Tuple[float, int]:
        """获取时间窗口统计数据"""
        with self.lock:
            if window_size in self.window_stats[metric_type][aggregation_level][target_id]:
                stat = self.window_stats[metric_type][aggregation_level][target_id][window_size]
                return stat.get_value(), stat.get_count()
            return 0.0, 0
    
    def reset_daily_stats(self):
        """重置日统计数据（日终处理）"""
        with self.lock:
            self.daily_stats.clear()
    
    def get_all_stats_for_target(self, target_id: str) -> Dict[str, Any]:
        """获取指定目标的所有统计信息"""
        result = {}
        with self.lock:
            for metric_type in MetricType:
                result[metric_type.value] = {}
                for level in AggregationLevel:
                    if target_id in self.daily_stats[metric_type][level]:
                        stat = self.daily_stats[metric_type][level][target_id]
                        result[metric_type.value][level.value] = {
                            "daily": {"value": stat.value, "count": stat.count},
                            "windows": {}
                        }
                        
                        # 添加时间窗口统计
                        if metric_type in self.window_stats and level in self.window_stats[metric_type]:
                            if target_id in self.window_stats[metric_type][level]:
                                for window_size, window_stat in self.window_stats[metric_type][level][target_id].items():
                                    result[metric_type.value][level.value]["windows"][f"{window_size}s"] = {
                                        "value": window_stat.get_value(),
                                        "count": window_stat.get_count()
                                    }
        return result