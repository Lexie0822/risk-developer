"""
Multi-dimensional metrics engine for risk control.
"""

from collections import defaultdict, deque
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
import time
import threading
from enum import Enum, auto
import heapq


class MetricType(Enum):
    """Metric types supported by the engine"""
    VOLUME = auto()          # 成交量
    AMOUNT = auto()          # 成交金额
    ORDER_COUNT = auto()     # 报单数量
    CANCEL_COUNT = auto()    # 撤单数量
    TRADE_COUNT = auto()     # 成交笔数
    

class AggregationType(Enum):
    """Aggregation types"""
    SUM = auto()
    COUNT = auto()
    AVG = auto()
    MAX = auto()
    MIN = auto()


@dataclass
class MetricDimension:
    """Dimension for metric aggregation"""
    name: str
    value: Any
    
    def __hash__(self):
        return hash((self.name, self.value))
    
    def __eq__(self, other):
        return self.name == other.name and self.value == other.value


@dataclass(frozen=True)
class TimeWindow:
    """Time window for metric calculation"""
    duration_ns: int  # Duration in nanoseconds
    slide_ns: Optional[int] = None  # Slide interval for sliding windows
    
    @property
    def duration_seconds(self) -> float:
        return self.duration_ns / 1e9
    
    @classmethod
    def seconds(cls, seconds: float) -> 'TimeWindow':
        """Create time window from seconds"""
        return cls(int(seconds * 1e9))
    
    @classmethod
    def minutes(cls, minutes: float) -> 'TimeWindow':
        """Create time window from minutes"""
        return cls.seconds(minutes * 60)
    
    @classmethod
    def hours(cls, hours: float) -> 'TimeWindow':
        """Create time window from hours"""
        return cls.minutes(hours * 60)
    
    @classmethod
    def days(cls, days: float) -> 'TimeWindow':
        """Create time window from days"""
        return cls.hours(days * 24)


@dataclass
class MetricPoint:
    """A single metric data point"""
    timestamp: int
    value: float
    dimensions: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        return self.timestamp < other.timestamp


class TimeWindowMetrics:
    """Metrics aggregated over a time window"""
    
    def __init__(self, window: TimeWindow, max_points: int = 10000):
        self.window = window
        self.max_points = max_points
        self.points: deque = deque(maxlen=max_points)
        self._lock = threading.RLock()
        self._sum = 0.0
        self._count = 0
        
    def add_point(self, timestamp: int, value: float):
        """Add a new data point"""
        with self._lock:
            # Remove expired points
            cutoff_time = timestamp - self.window.duration_ns
            while self.points and self.points[0].timestamp < cutoff_time:
                old_point = self.points.popleft()
                self._sum -= old_point.value
                self._count -= 1
            
            # Add new point
            point = MetricPoint(timestamp, value)
            self.points.append(point)
            self._sum += value
            self._count += 1
    
    def get_sum(self, current_time: Optional[int] = None) -> float:
        """Get sum of values in the window"""
        if current_time:
            self._cleanup_expired(current_time)
        with self._lock:
            return self._sum
    
    def get_count(self, current_time: Optional[int] = None) -> int:
        """Get count of values in the window"""
        if current_time:
            self._cleanup_expired(current_time)
        with self._lock:
            return self._count
    
    def get_avg(self, current_time: Optional[int] = None) -> float:
        """Get average of values in the window"""
        if current_time:
            self._cleanup_expired(current_time)
        with self._lock:
            return self._sum / self._count if self._count > 0 else 0.0
    
    def get_rate(self, current_time: Optional[int] = None) -> float:
        """Get rate per second"""
        if current_time:
            self._cleanup_expired(current_time)
        with self._lock:
            if self._count == 0:
                return 0.0
            duration_seconds = self.window.duration_seconds
            return self._sum / duration_seconds
    
    def _cleanup_expired(self, current_time: int):
        """Remove expired points"""
        with self._lock:
            cutoff_time = current_time - self.window.duration_ns
            while self.points and self.points[0].timestamp < cutoff_time:
                old_point = self.points.popleft()
                self._sum -= old_point.value
                self._count -= 1


class MultiDimensionalMetrics:
    """Multi-dimensional metrics engine"""
    
    def __init__(self):
        # Structure: metric_type -> dimensions -> window -> TimeWindowMetrics
        self.metrics: Dict[MetricType, Dict[Tuple[MetricDimension, ...], Dict[TimeWindow, TimeWindowMetrics]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        self._lock = threading.RLock()
        
        # Cache for fast lookups
        self._dimension_index: Dict[str, Set[Any]] = defaultdict(set)
        
    def record_metric(self, 
                     metric_type: MetricType,
                     value: float,
                     timestamp: int,
                     dimensions: List[MetricDimension],
                     windows: List[TimeWindow]):
        """Record a metric value"""
        with self._lock:
            # Convert dimensions to tuple for hashing
            dim_tuple = tuple(sorted(dimensions, key=lambda d: d.name))
            
            # Update dimension index
            for dim in dimensions:
                self._dimension_index[dim.name].add(dim.value)
            
            # Record in all specified windows
            for window in windows:
                if window not in self.metrics[metric_type][dim_tuple]:
                    self.metrics[metric_type][dim_tuple][window] = TimeWindowMetrics(window)
                
                self.metrics[metric_type][dim_tuple][window].add_point(timestamp, value)
    
    def get_metric(self,
                   metric_type: MetricType,
                   dimensions: List[MetricDimension],
                   window: TimeWindow,
                   aggregation: AggregationType = AggregationType.SUM,
                   current_time: Optional[int] = None) -> float:
        """Get metric value for specific dimensions and window"""
        with self._lock:
            dim_tuple = tuple(sorted(dimensions, key=lambda d: d.name))
            
            if (metric_type not in self.metrics or 
                dim_tuple not in self.metrics[metric_type] or
                window not in self.metrics[metric_type][dim_tuple]):
                return 0.0
            
            window_metrics = self.metrics[metric_type][dim_tuple][window]
            
            if aggregation == AggregationType.SUM:
                return window_metrics.get_sum(current_time)
            elif aggregation == AggregationType.COUNT:
                return float(window_metrics.get_count(current_time))
            elif aggregation == AggregationType.AVG:
                return window_metrics.get_avg(current_time)
            else:
                raise ValueError(f"Unsupported aggregation type: {aggregation}")
    
    def get_metric_by_dimension(self,
                               metric_type: MetricType,
                               dimension_name: str,
                               dimension_value: Any,
                               window: TimeWindow,
                               aggregation: AggregationType = AggregationType.SUM,
                               current_time: Optional[int] = None) -> float:
        """Get aggregated metric for a specific dimension value across all combinations"""
        with self._lock:
            total = 0.0
            count = 0
            
            # Find all dimension combinations that include the specified dimension
            for dim_tuple, windows_dict in self.metrics[metric_type].items():
                # Check if this combination includes our dimension
                for dim in dim_tuple:
                    if dim.name == dimension_name and dim.value == dimension_value:
                        if window in windows_dict:
                            window_metrics = windows_dict[window]
                            if aggregation == AggregationType.SUM:
                                total += window_metrics.get_sum(current_time)
                                count += 1
                            elif aggregation == AggregationType.COUNT:
                                total += window_metrics.get_count(current_time)
                                count += 1
                        break
            
            if aggregation == AggregationType.AVG and count > 0:
                return total / count
            return total
    
    def get_top_n(self,
                  metric_type: MetricType,
                  dimension_name: str,
                  window: TimeWindow,
                  n: int = 10,
                  aggregation: AggregationType = AggregationType.SUM,
                  current_time: Optional[int] = None) -> List[Tuple[Any, float]]:
        """Get top N dimension values by metric"""
        with self._lock:
            # Aggregate by dimension value
            value_totals = {}
            
            for dimension_value in self._dimension_index[dimension_name]:
                total = self.get_metric_by_dimension(
                    metric_type, dimension_name, dimension_value, 
                    window, aggregation, current_time
                )
                if total > 0:
                    value_totals[dimension_value] = total
            
            # Get top N
            return heapq.nlargest(n, value_totals.items(), key=lambda x: x[1])
    
    def clear_expired(self, current_time: int):
        """Clear expired data from all metrics"""
        with self._lock:
            for metric_type in list(self.metrics.keys()):
                for dim_tuple in list(self.metrics[metric_type].keys()):
                    for window in list(self.metrics[metric_type][dim_tuple].keys()):
                        self.metrics[metric_type][dim_tuple][window]._cleanup_expired(current_time)
                        
                        # Remove empty windows
                        if self.metrics[metric_type][dim_tuple][window]._count == 0:
                            del self.metrics[metric_type][dim_tuple][window]
                    
                    # Remove empty dimension combinations
                    if not self.metrics[metric_type][dim_tuple]:
                        del self.metrics[metric_type][dim_tuple]
                
                # Remove empty metric types
                if not self.metrics[metric_type]:
                    del self.metrics[metric_type]


class MetricsCollector:
    """High-level metrics collector for the risk control system"""
    
    def __init__(self):
        self.engine = MultiDimensionalMetrics()
        self.default_windows = [
            TimeWindow.seconds(1),    # 1秒窗口
            TimeWindow.seconds(60),   # 1分钟窗口
            TimeWindow.minutes(5),    # 5分钟窗口
            TimeWindow.hours(1),      # 1小时窗口
            TimeWindow.days(1),       # 1天窗口
        ]
    
    def record_trade(self, trade, order):
        """Record trade metrics"""
        timestamp = trade.timestamp
        
        # Dimensions
        dimensions = [
            MetricDimension("account", order.account_id),
            MetricDimension("contract", order.contract_id),
            MetricDimension("product", order.product_id),
        ]
        
        # Record volume
        self.engine.record_metric(
            MetricType.VOLUME,
            trade.volume,
            timestamp,
            dimensions,
            self.default_windows
        )
        
        # Record amount
        self.engine.record_metric(
            MetricType.AMOUNT,
            trade.amount,
            timestamp,
            dimensions,
            self.default_windows
        )
        
        # Record trade count
        self.engine.record_metric(
            MetricType.TRADE_COUNT,
            1,
            timestamp,
            dimensions,
            self.default_windows
        )
    
    def record_order(self, order):
        """Record order metrics"""
        timestamp = order.timestamp
        
        # Dimensions
        dimensions = [
            MetricDimension("account", order.account_id),
            MetricDimension("contract", order.contract_id),
            MetricDimension("product", order.product_id),
        ]
        
        # Record order count
        self.engine.record_metric(
            MetricType.ORDER_COUNT,
            1,
            timestamp,
            dimensions,
            self.default_windows
        )
    
    def get_account_volume(self, account_id: str, window: TimeWindow, current_time: Optional[int] = None) -> float:
        """Get total volume for an account"""
        return self.engine.get_metric_by_dimension(
            MetricType.VOLUME,
            "account",
            account_id,
            window,
            AggregationType.SUM,
            current_time
        )
    
    def get_account_order_rate(self, account_id: str, window: TimeWindow, current_time: Optional[int] = None) -> float:
        """Get order rate per second for an account"""
        count = self.engine.get_metric_by_dimension(
            MetricType.ORDER_COUNT,
            "account",
            account_id,
            window,
            AggregationType.SUM,
            current_time
        )
        return count / window.duration_seconds
    
    def get_product_volume(self, product_id: str, window: TimeWindow, current_time: Optional[int] = None) -> float:
        """Get total volume for a product"""
        return self.engine.get_metric_by_dimension(
            MetricType.VOLUME,
            "product",
            product_id,
            window,
            AggregationType.SUM,
            current_time
        )
    
    def get_top_accounts_by_volume(self, window: TimeWindow, n: int = 10, current_time: Optional[int] = None) -> List[Tuple[str, float]]:
        """Get top N accounts by trading volume"""
        return self.engine.get_top_n(
            MetricType.VOLUME,
            "account",
            window,
            n,
            AggregationType.SUM,
            current_time
        )