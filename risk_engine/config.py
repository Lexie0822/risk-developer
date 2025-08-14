from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from enum import Enum

from .metrics import MetricType
from .actions import Action


class StatsDimension(str, Enum):
	"""统计维度枚举。"""
	ACCOUNT = "account"
	CONTRACT = "contract"
	PRODUCT = "product"
	EXCHANGE = "exchange"
	ACCOUNT_GROUP = "account_group"


@dataclass
class VolumeLimitRuleConfig:
	"""成交量限制规则配置。"""
	threshold: float
	dimension: StatsDimension = StatsDimension.PRODUCT
	reset_daily: bool = True
	metric: MetricType = MetricType.TRADE_VOLUME


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
class RiskEngineConfig:
	"""风控引擎配置。"""
	contract_to_product: Dict[str, str] = field(default_factory=dict)
	contract_to_exchange: Dict[str, str] = field(default_factory=dict)
	volume_limit: Optional[VolumeLimitRuleConfig] = None
	order_rate_limit: Optional[OrderRateLimitRuleConfig] = None
	
	# 性能调优参数
	num_shards: int = 64  # 分片锁数量
	max_queue_size: int = 100000  # 最大队列大小
	batch_size: int = 1000  # 批处理大小
	worker_threads: int = 4  # 工作线程数
	
	# 监控参数
	enable_metrics: bool = True
	enable_tracing: bool = False
	metrics_interval_ms: int = 1000  # 指标收集间隔


@dataclass
class DynamicRuleConfig:
	"""动态规则配置，支持热更新。"""
	rule_id: str
	rule_type: str  # "volume_limit" | "order_rate_limit" | "custom"
	enabled: bool = True
	priority: int = 100  # 优先级，数字越小优先级越高
	config: Dict = field(default_factory=dict)
	
	# 时间窗口配置
	effective_from: Optional[int] = None  # 生效时间戳（纳秒）
	effective_until: Optional[int] = None  # 失效时间戳（纳秒）
	
	# 条件配置
	conditions: List[Dict] = field(default_factory=list)  # 触发条件
	actions: List[str] = field(default_factory=list)  # 处置动作


@dataclass
class RiskEngineRuntimeConfig:
	"""运行时配置，支持动态调整。"""
	rules: List[DynamicRuleConfig] = field(default_factory=list)
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