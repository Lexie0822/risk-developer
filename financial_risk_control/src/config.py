"""
Configuration system for risk control rules.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
import json
from pathlib import Path
import threading

# Try to import yaml, but don't fail if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from .models import ActionType
from .metrics import MetricType, TimeWindow


class ConfigFormat(Enum):
    """Configuration file format"""
    JSON = "json"
    YAML = "yaml"
    DICT = "dict"


@dataclass
class MetricConfig:
    """Configuration for a metric"""
    metric_type: MetricType
    threshold: float
    window: TimeWindow
    dimensions: List[str] = field(default_factory=list)
    aggregation: str = "SUM"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "metric_type": self.metric_type.name,
            "threshold": self.threshold,
            "window_seconds": self.window.duration_seconds,
            "dimensions": self.dimensions,
            "aggregation": self.aggregation
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MetricConfig':
        """Create from dictionary"""
        return cls(
            metric_type=MetricType[data["metric_type"]],
            threshold=data["threshold"],
            window=TimeWindow.seconds(data["window_seconds"]),
            dimensions=data.get("dimensions", []),
            aggregation=data.get("aggregation", "SUM")
        )


@dataclass
class RuleConfig:
    """Configuration for a risk control rule"""
    rule_id: str
    name: str
    description: str
    enabled: bool = True
    priority: int = 0  # Higher priority rules are evaluated first
    metrics: List[MetricConfig] = field(default_factory=list)
    actions: List[ActionType] = field(default_factory=list)
    cooldown_seconds: float = 0  # Cooldown period before rule can trigger again
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "priority": self.priority,
            "metrics": [m.to_dict() for m in self.metrics],
            "actions": [a.name for a in self.actions],
            "cooldown_seconds": self.cooldown_seconds,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RuleConfig':
        """Create from dictionary"""
        return cls(
            rule_id=data["rule_id"],
            name=data["name"],
            description=data["description"],
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
            metrics=[MetricConfig.from_dict(m) for m in data.get("metrics", [])],
            actions=[ActionType[a] for a in data.get("actions", [])],
            cooldown_seconds=data.get("cooldown_seconds", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class RiskControlConfig:
    """Main configuration for the risk control system"""
    rules: List[RuleConfig] = field(default_factory=list)
    global_settings: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rules": [r.to_dict() for r in self.rules],
            "global_settings": self.global_settings
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RiskControlConfig':
        """Create from dictionary"""
        return cls(
            rules=[RuleConfig.from_dict(r) for r in data.get("rules", [])],
            global_settings=data.get("global_settings", {})
        )
    
    def add_rule(self, rule: RuleConfig):
        """Add a new rule"""
        self.rules.append(rule)
        # Sort by priority (descending)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
    
    def remove_rule(self, rule_id: str):
        """Remove a rule by ID"""
        self.rules = [r for r in self.rules if r.rule_id != rule_id]
    
    def get_rule(self, rule_id: str) -> Optional[RuleConfig]:
        """Get a rule by ID"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None
    
    def update_rule(self, rule_id: str, updates: Dict[str, Any]):
        """Update a rule's configuration"""
        rule = self.get_rule(rule_id)
        if rule:
            for key, value in updates.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
            # Re-sort if priority changed
            if "priority" in updates:
                self.rules.sort(key=lambda r: r.priority, reverse=True)


class ConfigManager:
    """Manages configuration loading, saving, and hot-reloading"""
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        self.config_path = Path(config_path) if config_path else None
        self.config = RiskControlConfig()
        self._lock = threading.RLock()
        self._watchers = []
        
        # Load initial configuration if path provided
        if self.config_path and self.config_path.exists():
            self.load()
    
    def load(self, path: Optional[Union[str, Path]] = None, format: ConfigFormat = ConfigFormat.JSON):
        """Load configuration from file"""
        path = Path(path) if path else self.config_path
        if not path or not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        with self._lock:
            if format == ConfigFormat.JSON:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            elif format == ConfigFormat.YAML:
                if not HAS_YAML:
                    raise ImportError("PyYAML is required for YAML format. Install with: pip install pyyaml")
                with open(path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            self.config = RiskControlConfig.from_dict(data)
            self._notify_watchers()
    
    def save(self, path: Optional[Union[str, Path]] = None, format: ConfigFormat = ConfigFormat.JSON):
        """Save configuration to file"""
        path = Path(path) if path else self.config_path
        if not path:
            raise ValueError("No path specified for saving configuration")
        
        with self._lock:
            data = self.config.to_dict()
            
            if format == ConfigFormat.JSON:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            elif format == ConfigFormat.YAML:
                if not HAS_YAML:
                    raise ImportError("PyYAML is required for YAML format. Install with: pip install pyyaml")
                with open(path, 'w', encoding='utf-8') as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            else:
                raise ValueError(f"Unsupported format: {format}")
    
    def load_from_dict(self, data: Dict[str, Any]):
        """Load configuration from dictionary"""
        with self._lock:
            self.config = RiskControlConfig.from_dict(data)
            self._notify_watchers()
    
    def add_watcher(self, callback):
        """Add a callback to be notified of configuration changes"""
        self._watchers.append(callback)
    
    def _notify_watchers(self):
        """Notify all watchers of configuration change"""
        for callback in self._watchers:
            try:
                callback(self.config)
            except Exception as e:
                print(f"Error notifying watcher: {e}")
    
    def create_default_config(self) -> RiskControlConfig:
        """Create a default configuration with common rules"""
        config = RiskControlConfig()
        
        # Rule 1: Account daily volume limit
        volume_rule = RuleConfig(
            rule_id="account_daily_volume_limit",
            name="账户日成交量限制",
            description="当账户当日成交量超过1000手时，暂停该账户交易",
            enabled=True,
            priority=100,
            metrics=[
                MetricConfig(
                    metric_type=MetricType.VOLUME,
                    threshold=1000,
                    window=TimeWindow.days(1),
                    dimensions=["account"]
                )
            ],
            actions=[ActionType.SUSPEND_ACCOUNT],
            cooldown_seconds=300  # 5 minutes cooldown
        )
        config.add_rule(volume_rule)
        
        # Rule 2: Order frequency control
        frequency_rule = RuleConfig(
            rule_id="account_order_frequency_limit",
            name="账户报单频率控制",
            description="当账户每秒报单数超过50次时，暂停报单",
            enabled=True,
            priority=90,
            metrics=[
                MetricConfig(
                    metric_type=MetricType.ORDER_COUNT,
                    threshold=50,
                    window=TimeWindow.seconds(1),
                    dimensions=["account"]
                )
            ],
            actions=[ActionType.SUSPEND_ORDER],
            cooldown_seconds=60  # 1 minute cooldown
        )
        config.add_rule(frequency_rule)
        
        # Rule 3: Product volume monitoring (warning only)
        product_rule = RuleConfig(
            rule_id="product_volume_warning",
            name="产品成交量预警",
            description="当产品小时成交量超过10000手时，发出预警",
            enabled=True,
            priority=50,
            metrics=[
                MetricConfig(
                    metric_type=MetricType.VOLUME,
                    threshold=10000,
                    window=TimeWindow.hours(1),
                    dimensions=["product"]
                )
            ],
            actions=[ActionType.WARNING],
            cooldown_seconds=600  # 10 minutes cooldown
        )
        config.add_rule(product_rule)
        
        # Global settings
        config.global_settings = {
            "max_concurrent_orders": 1000,
            "max_daily_trades": 50000,
            "enable_pre_trade_check": True,
            "enable_post_trade_check": True,
            "metric_cleanup_interval_seconds": 300,
            "performance_monitoring": {
                "enabled": True,
                "sample_rate": 0.1
            }
        }
        
        return config


# Example configuration builders for common scenarios
class RuleBuilder:
    """Helper class to build rule configurations"""
    
    @staticmethod
    def volume_limit_rule(
        rule_id: str,
        account_id: Optional[str] = None,
        threshold: float = 1000,
        window_hours: float = 24,
        actions: List[ActionType] = None
    ) -> RuleConfig:
        """Create a volume limit rule"""
        if actions is None:
            actions = [ActionType.SUSPEND_ACCOUNT]
        
        dimensions = ["account"] if account_id is None else []
        
        return RuleConfig(
            rule_id=rule_id,
            name=f"Volume limit rule ({threshold} in {window_hours}h)",
            description=f"Limit volume to {threshold} in {window_hours} hours",
            metrics=[
                MetricConfig(
                    metric_type=MetricType.VOLUME,
                    threshold=threshold,
                    window=TimeWindow.hours(window_hours),
                    dimensions=dimensions
                )
            ],
            actions=actions,
            metadata={"account_id": account_id} if account_id else {}
        )
    
    @staticmethod
    def frequency_limit_rule(
        rule_id: str,
        metric_type: MetricType = MetricType.ORDER_COUNT,
        threshold: float = 50,
        window_seconds: float = 1,
        actions: List[ActionType] = None
    ) -> RuleConfig:
        """Create a frequency limit rule"""
        if actions is None:
            actions = [ActionType.SUSPEND_ORDER]
        
        return RuleConfig(
            rule_id=rule_id,
            name=f"Frequency limit rule ({threshold}/{window_seconds}s)",
            description=f"Limit {metric_type.name} to {threshold} per {window_seconds} seconds",
            metrics=[
                MetricConfig(
                    metric_type=metric_type,
                    threshold=threshold,
                    window=TimeWindow.seconds(window_seconds),
                    dimensions=["account"]
                )
            ],
            actions=actions
        )