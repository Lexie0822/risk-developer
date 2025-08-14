"""
统计引擎模块
支持多维度、多指标的实时统计
"""
from collections import defaultdict
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import threading
from dataclasses import dataclass, field
import time

from .models import Order, Trade
from .config import DimensionType, MetricType, get_product_by_contract


@dataclass
class TimeWindow:
    """时间窗口定义"""
    window_size: int  # 窗口大小（秒）
    data: list = field(default_factory=list)  # [(timestamp, value), ...]
    
    def add(self, timestamp: int, value: float):
        """添加数据点"""
        self.data.append((timestamp, value))
        self._clean_expired(timestamp)
    
    def _clean_expired(self, current_timestamp: int):
        """清理过期数据"""
        cutoff_time = current_timestamp - self.window_size * 1_000_000_000  # 转换为纳秒
        self.data = [(ts, val) for ts, val in self.data if ts > cutoff_time]
    
    def get_sum(self, current_timestamp: int) -> float:
        """获取窗口内数据总和"""
        self._clean_expired(current_timestamp)
        return sum(val for _, val in self.data)
    
    def get_count(self, current_timestamp: int) -> int:
        """获取窗口内数据点数量"""
        self._clean_expired(current_timestamp)
        return len(self.data)


class StatisticsEngine:
    """多维度统计引擎"""
    
    def __init__(self):
        # 统计数据存储：dimension_type -> dimension_key -> metric_type -> value
        self._stats: Dict[DimensionType, Dict[str, Dict[MetricType, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float))
        )
        
        # 时间窗口统计：dimension_type -> dimension_key -> metric_type -> TimeWindow
        self._time_windows: Dict[DimensionType, Dict[str, Dict[MetricType, TimeWindow]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        
        # 日统计重置时间
        self._daily_reset_time = None
        self._lock = threading.RLock()
        
        # 订单缓存，用于关联trade
        self._order_cache: Dict[int, Order] = {}
    
    def _get_dimension_keys(self, order: Order = None, trade: Trade = None) -> Dict[DimensionType, str]:
        """获取各维度的key"""
        keys = {}
        
        if order:
            keys[DimensionType.ACCOUNT] = order.account_id
            keys[DimensionType.CONTRACT] = order.contract_id
            product = get_product_by_contract(order.contract_id)
            if product:
                keys[DimensionType.PRODUCT] = product
        
        if trade:
            if trade.account_id:
                keys[DimensionType.ACCOUNT] = trade.account_id
            if trade.contract_id:
                keys[DimensionType.CONTRACT] = trade.contract_id
                product = get_product_by_contract(trade.contract_id)
                if product:
                    keys[DimensionType.PRODUCT] = product
        
        return keys
    
    def _check_daily_reset(self, timestamp: int):
        """检查是否需要日重置"""
        current_date = datetime.fromtimestamp(timestamp / 1_000_000_000).date()
        
        if self._daily_reset_time is None:
            self._daily_reset_time = current_date
            return
        
        if current_date > self._daily_reset_time:
            # 重置日统计
            with self._lock:
                for dim_type in [DimensionType.ACCOUNT, DimensionType.CONTRACT, DimensionType.PRODUCT]:
                    if dim_type in self._stats:
                        for dim_key in self._stats[dim_type]:
                            # 只重置非频率类指标
                            for metric in [MetricType.TRADE_VOLUME, MetricType.TRADE_AMOUNT, 
                                         MetricType.ORDER_COUNT, MetricType.CANCEL_COUNT]:
                                if metric in self._stats[dim_type][dim_key]:
                                    self._stats[dim_type][dim_key][metric] = 0
                
                self._daily_reset_time = current_date
    
    def on_order(self, order: Order):
        """处理订单事件"""
        with self._lock:
            self._check_daily_reset(order.timestamp)
            
            # 缓存订单
            self._order_cache[order.oid] = order
            
            # 获取维度keys
            dimension_keys = self._get_dimension_keys(order=order)
            
            # 更新订单数量统计
            for dim_type, dim_key in dimension_keys.items():
                self._stats[dim_type][dim_key][MetricType.ORDER_COUNT] += 1
                
                # 更新订单频率统计（1秒窗口）
                if dim_type == DimensionType.ACCOUNT:
                    if MetricType.ORDER_FREQUENCY not in self._time_windows[dim_type][dim_key]:
                        self._time_windows[dim_type][dim_key][MetricType.ORDER_FREQUENCY] = TimeWindow(1)
                    
                    self._time_windows[dim_type][dim_key][MetricType.ORDER_FREQUENCY].add(
                        order.timestamp, 1
                    )
    
    def on_trade(self, trade: Trade):
        """处理成交事件"""
        with self._lock:
            self._check_daily_reset(trade.timestamp)
            
            # 从缓存获取订单信息
            order = self._order_cache.get(trade.oid)
            if order:
                trade.account_id = order.account_id
                trade.contract_id = order.contract_id
                trade.direction = order.direction
            
            # 获取维度keys
            dimension_keys = self._get_dimension_keys(trade=trade)
            
            # 更新成交统计
            for dim_type, dim_key in dimension_keys.items():
                self._stats[dim_type][dim_key][MetricType.TRADE_VOLUME] += trade.volume
                self._stats[dim_type][dim_key][MetricType.TRADE_AMOUNT] += trade.get_trade_amount()
    
    def get_statistic(self, dimension_type: DimensionType, dimension_key: str, 
                     metric_type: MetricType, current_timestamp: int = None) -> float:
        """获取统计值"""
        with self._lock:
            if metric_type == MetricType.ORDER_FREQUENCY:
                # 频率类指标从时间窗口获取
                if (dimension_type in self._time_windows and 
                    dimension_key in self._time_windows[dimension_type] and
                    metric_type in self._time_windows[dimension_type][dimension_key]):
                    
                    if current_timestamp is None:
                        current_timestamp = int(time.time() * 1_000_000_000)
                    
                    window = self._time_windows[dimension_type][dimension_key][metric_type]
                    return window.get_count(current_timestamp)
                return 0.0
            else:
                # 累计类指标直接返回
                return self._stats[dimension_type][dimension_key][metric_type]
    
    def get_all_statistics(self, dimension_type: DimensionType, 
                          dimension_key: str) -> Dict[MetricType, float]:
        """获取某个维度的所有统计数据"""
        with self._lock:
            result = {}
            current_timestamp = int(time.time() * 1_000_000_000)
            
            # 获取累计统计
            if dimension_type in self._stats and dimension_key in self._stats[dimension_type]:
                result.update(self._stats[dimension_type][dimension_key])
            
            # 获取时间窗口统计
            if dimension_type in self._time_windows and dimension_key in self._time_windows[dimension_type]:
                for metric_type, window in self._time_windows[dimension_type][dimension_key].items():
                    if metric_type == MetricType.ORDER_FREQUENCY:
                        result[metric_type] = window.get_count(current_timestamp)
            
            return result
    
    def clear_statistics(self):
        """清空所有统计数据（用于测试）"""
        with self._lock:
            self._stats.clear()
            self._time_windows.clear()
            self._order_cache.clear()
            self._daily_reset_time = None