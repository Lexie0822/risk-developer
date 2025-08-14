from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union, Any
from enum import Enum

from .metrics import MetricType
from .actions import Action


class StatsDimension(str, Enum):
    """统计维度枚举（可扩展）。"""
    ACCOUNT = "account"
    CONTRACT = "contract"
    PRODUCT = "product"
    EXCHANGE = "exchange"
    ACCOUNT_GROUP = "account_group"
    # 扩展维度
    SECTOR = "sector"          # 行业分类
    STRATEGY = "strategy"      # 策略维度
    TRADER = "trader"          # 交易员维度
    BOOK = "book"              # 账簿维度
    REGION = "region"          # 地区维度


@dataclass
class VolumeLimitRuleConfig:
    """成交量限制规则配置。"""
    threshold: float
    dimension: StatsDimension = StatsDimension.PRODUCT
    reset_daily: bool = True
    metric: MetricType = MetricType.TRADE_VOLUME
    # 多维度组合支持
    dimensions: Optional[List[StatsDimension]] = None
    # 扩展配置
    custom_dimensions: Optional[Dict[str, str]] = None


@dataclass
class OrderRateLimitRuleConfig:
    """报单频率限制规则配置。

    兼容两种时间窗口配置：
    - window_ns: 以纳秒为单位（与旧用法一致）
    - window_seconds: 以秒为单位（与部分示例一致）
    二者任意提供其一即可，未提供的将自动换算。
    """
    threshold: int
    # 兼容参数：可二选一提供
    window_ns: Optional[int] = None
    window_seconds: Optional[int] = None
    dimension: StatsDimension = StatsDimension.ACCOUNT
    # 多维度组合支持
    dimensions: Optional[List[StatsDimension]] = None

    def __post_init__(self) -> None:
        # 若均未提供，设为 1 秒窗口
        if self.window_ns is None and self.window_seconds is None:
            self.window_ns = 1_000_000_000
            self.window_seconds = 1
            return
        # 若仅提供秒，则换算为纳秒
        if self.window_ns is None and self.window_seconds is not None:
            self.window_ns = int(self.window_seconds) * 1_000_000_000
            return
        # 若仅提供纳秒，则换算为秒（至少 1 秒）
        if self.window_seconds is None and self.window_ns is not None:
            self.window_seconds = max(1, self.window_ns // 1_000_000_000)


@dataclass
class CancelRuleLimitConfig:
    """撤单规则配置（扩展点）。"""
    threshold: int  # 阈值
    metric: MetricType = MetricType.CANCEL_COUNT  # CANCEL_COUNT, CANCEL_VOLUME, CANCEL_RATE
    window_seconds: int = 1
    dimension: StatsDimension = StatsDimension.ACCOUNT
    actions: List[Action] = field(default_factory=lambda: [Action.SUSPEND_ORDERING])


@dataclass
class RiskEngineConfig:
    """风控引擎配置。"""
    contract_to_product: Dict[str, str] = field(default_factory=dict)
    contract_to_exchange: Dict[str, str] = field(default_factory=dict)
    # 扩展维度映射
    contract_to_sector: Dict[str, str] = field(default_factory=dict)  # 合约 -> 行业
    account_to_group: Dict[str, str] = field(default_factory=dict)    # 账户 -> 组
    account_to_trader: Dict[str, str] = field(default_factory=dict)   # 账户 -> 交易员
    
    # 规则配置
    volume_limit: Optional[VolumeLimitRuleConfig] = None
    order_rate_limit: Optional[OrderRateLimitRuleConfig] = None
    cancel_rule_limit: Optional[CancelRuleLimitConfig] = None  # 撤单规则
    
    # 性能调优参数
    num_shards: int = 64  # 分片锁数量
    max_queue_size: int = 100000  # 最大队列大小
    batch_size: int = 1000  # 批处理大小
    worker_threads: int = 4  # 工作线程数
    
    # 监控参数
    enable_metrics: bool = True
    enable_tracing: bool = False
    metrics_interval_ms: int = 1000  # 指标收集间隔
    
    # 扩展配置
    custom_dimension_mappings: Dict[str, Dict[str, str]] = field(default_factory=dict)
    custom_rule_configs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DynamicRuleConfig:
    """动态规则配置，支持热更新。"""
    rule_id: str
    rule_type: str  # "volume_limit" | "order_rate_limit" | "cancel_rate_limit" | "custom"
    enabled: bool = True
    priority: int = 100  # 优先级，数字越小优先级越高
    config: Dict = field(default_factory=dict)
    
    # 时间窗口配置
    effective_from: Optional[int] = None  # 生效时间戳（纳秒）
    effective_until: Optional[int] = None  # 失效时间戳（纳秒）
    
    # 条件配置
    conditions: List[Dict] = field(default_factory=list)  # 触发条件
    actions: List[str] = field(default_factory=list)  # 处置动作
    
    # 多维度配置
    dimensions: List[str] = field(default_factory=list)  # 统计维度
    dimension_filters: Dict[str, List[str]] = field(default_factory=dict)  # 维度过滤


@dataclass
class MultiDimensionRuleConfig:
    """多维度规则配置。"""
    rule_id: str
    metric_type: MetricType
    threshold: float
    dimensions: List[StatsDimension]  # 多维度组合
    aggregation_method: str = "sum"  # sum, max, min, avg
    time_window: Optional[int] = None  # 时间窗口（秒）
    actions: List[Action] = field(default_factory=lambda: [Action.SUSPEND_ACCOUNT_TRADING])


@dataclass
class RiskEngineRuntimeConfig:
    """运行时配置，支持动态调整。"""
    rules: List[DynamicRuleConfig] = field(default_factory=list)
    multi_dimension_rules: List[MultiDimensionRuleConfig] = field(default_factory=list)
    performance_tuning: Dict = field(default_factory=dict)
    monitoring: Dict = field(default_factory=dict)
    
    def add_rule(self, rule: DynamicRuleConfig) -> None:
        """添加新规则。"""
        self.rules.append(rule)
        self.rules.sort(key=lambda x: x.priority)
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除规则。"""
        for i, rule in enumerate(self.rules):
            if rule.rule_id == rule_id:
                del self.rules[i]
                return True
        return False
    
    def update_rule(self, rule_id: str, updates: Dict) -> bool:
        """更新规则配置。"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                for key, value in updates.items():
                    if hasattr(rule, key):
                        setattr(rule, key, value)
                return True
        return False
    
    def add_multi_dimension_rule(self, rule: MultiDimensionRuleConfig) -> None:
        """添加多维度规则。"""
        self.multi_dimension_rules.append(rule)
    
    def get_rules_by_dimension(self, dimension: StatsDimension) -> List[DynamicRuleConfig]:
        """按维度获取规则。"""
        return [rule for rule in self.rules if dimension.value in rule.dimensions]


@dataclass
class ExtensionConfig:
    """扩展配置，用于插件和自定义功能。"""
    plugin_configs: Dict[str, Dict] = field(default_factory=dict)
    custom_metrics: Dict[str, str] = field(default_factory=dict)  # 自定义指标
    custom_actions: Dict[str, str] = field(default_factory=dict)  # 自定义动作
    custom_dimensions: Dict[str, Any] = field(default_factory=dict)  # 自定义维度