"""
Risk control rules implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Set
import time
import threading
from collections import defaultdict

from .models import Order, Trade, Action, ActionType, RiskEvent
from .metrics import MetricsCollector, MetricType, TimeWindow, MetricDimension
from .config import RuleConfig, MetricConfig


@dataclass
class RuleContext:
    """Context for rule evaluation"""
    order: Optional[Order] = None
    trade: Optional[Trade] = None
    current_time: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def get_current_time(self) -> int:
        """Get current time in nanoseconds"""
        if self.current_time:
            return self.current_time
        return int(time.time() * 1e9)


@dataclass
class RuleResult:
    """Result of rule evaluation"""
    triggered: bool
    actions: List[Action] = field(default_factory=list)
    events: List[RiskEvent] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    reason: str = ""


class Rule(ABC):
    """Abstract base class for risk control rules"""
    
    def __init__(self, rule_id: str, name: str, description: str = ""):
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.enabled = True
        self.last_triggered_time: Dict[str, int] = {}  # key -> last trigger time
        self.cooldown_ns = 0
        self._lock = threading.RLock()
    
    @abstractmethod
    def evaluate(self, context: RuleContext, metrics_collector: MetricsCollector) -> RuleResult:
        """Evaluate the rule and return result"""
        pass
    
    def check_cooldown(self, key: str, current_time: int) -> bool:
        """Check if rule is in cooldown period"""
        with self._lock:
            if key in self.last_triggered_time:
                elapsed = current_time - self.last_triggered_time[key]
                return elapsed < self.cooldown_ns
            return False
    
    def update_trigger_time(self, key: str, current_time: int):
        """Update last trigger time"""
        with self._lock:
            self.last_triggered_time[key] = current_time


class MetricBasedRule(Rule):
    """Rule based on metric thresholds"""
    
    def __init__(self, config: RuleConfig):
        super().__init__(config.rule_id, config.name, config.description)
        self.config = config
        self.enabled = config.enabled
        self.cooldown_ns = int(config.cooldown_seconds * 1e9)
        self.priority = config.priority
    
    def evaluate(self, context: RuleContext, metrics_collector: MetricsCollector) -> RuleResult:
        """Evaluate metric-based rule"""
        if not self.enabled:
            return RuleResult(triggered=False)
        
        current_time = context.get_current_time()
        result = RuleResult(triggered=False)
        
        # Determine the entity to check (account, contract, product)
        entity_key = self._get_entity_key(context)
        if not entity_key:
            return result
        
        # Check cooldown
        if self.check_cooldown(entity_key, current_time):
            return result
        
        # Evaluate all metric conditions
        all_conditions_met = True
        metric_values = {}
        
        for metric_config in self.config.metrics:
            metric_value = self._get_metric_value(
                context, metrics_collector, metric_config, current_time
            )
            metric_values[metric_config.metric_type.name] = metric_value
            
            if metric_value < metric_config.threshold:
                all_conditions_met = False
                break
        
        result.metrics = metric_values
        
        if all_conditions_met:
            result.triggered = True
            result.reason = self._generate_reason(metric_values)
            
            # Generate actions
            for action_type in self.config.actions:
                action = self._create_action(action_type, context, result.reason)
                result.actions.append(action)
            
            # Generate risk event
            event = RiskEvent(
                event_type=f"RULE_TRIGGERED_{self.rule_id}",
                severity="HIGH" if ActionType.SUSPEND_ACCOUNT in self.config.actions else "MEDIUM",
                account_id=context.order.account_id if context.order else None,
                contract_id=context.order.contract_id if context.order else None,
                description=result.reason,
                metrics=metric_values
            )
            result.events.append(event)
            
            # Update trigger time
            self.update_trigger_time(entity_key, current_time)
        
        return result
    
    def _get_entity_key(self, context: RuleContext) -> Optional[str]:
        """Get the entity key for cooldown tracking"""
        if not context.order:
            return None
        
        # Determine key based on rule dimensions
        if self.config.metrics:
            dimensions = self.config.metrics[0].dimensions
            if "account" in dimensions:
                return f"account:{context.order.account_id}"
            elif "contract" in dimensions:
                return f"contract:{context.order.contract_id}"
            elif "product" in dimensions:
                return f"product:{context.order.product_id}"
        
        return context.order.account_id
    
    def _get_metric_value(self, context: RuleContext, metrics_collector: MetricsCollector, 
                         metric_config: MetricConfig, current_time: int) -> float:
        """Get metric value based on configuration"""
        if not context.order:
            return 0.0
        
        # Build dimensions based on configuration
        dimensions = []
        for dim_name in metric_config.dimensions:
            if dim_name == "account":
                dimensions.append(MetricDimension("account", context.order.account_id))
            elif dim_name == "contract":
                dimensions.append(MetricDimension("contract", context.order.contract_id))
            elif dim_name == "product":
                dimensions.append(MetricDimension("product", context.order.product_id))
        
        # Get metric value
        if metric_config.metric_type == MetricType.VOLUME:
            return metrics_collector.get_account_volume(
                context.order.account_id, metric_config.window, current_time
            )
        elif metric_config.metric_type == MetricType.ORDER_COUNT:
            return metrics_collector.get_account_order_rate(
                context.order.account_id, metric_config.window, current_time
            ) * metric_config.window.duration_seconds
        else:
            # Generic metric retrieval
            from .metrics import AggregationType
            return metrics_collector.engine.get_metric(
                metric_config.metric_type,
                dimensions,
                metric_config.window,
                AggregationType[metric_config.aggregation],
                current_time
            )
    
    def _generate_reason(self, metric_values: Dict[str, float]) -> str:
        """Generate reason for rule trigger"""
        parts = []
        for metric_config in self.config.metrics:
            metric_name = metric_config.metric_type.name
            if metric_name in metric_values:
                value = metric_values[metric_name]
                threshold = metric_config.threshold
                parts.append(f"{metric_name}={value:.2f} (阈值={threshold})")
        
        return f"{self.name}: {', '.join(parts)}"
    
    def _create_action(self, action_type: ActionType, context: RuleContext, reason: str) -> Action:
        """Create action based on type and context"""
        action = Action(
            action_type=action_type,
            reason=reason,
            metadata={"rule_id": self.rule_id, "rule_name": self.name}
        )
        
        if context.order:
            action.account_id = context.order.account_id
            action.contract_id = context.order.contract_id
            action.product_id = context.order.product_id
        
        return action


class VolumeRule(MetricBasedRule):
    """Specialized rule for volume limits"""
    
    def __init__(self, rule_id: str, account_id: Optional[str] = None, 
                 threshold: float = 1000, window: Optional[TimeWindow] = None):
        # Create configuration
        if window is None:
            window = TimeWindow.days(1)
        
        metric_config = MetricConfig(
            metric_type=MetricType.VOLUME,
            threshold=threshold,
            window=window,
            dimensions=["account"]
        )
        
        config = RuleConfig(
            rule_id=rule_id,
            name=f"Volume limit ({threshold} in {window.duration_seconds/3600:.1f}h)",
            description=f"Suspend account when volume exceeds {threshold}",
            metrics=[metric_config],
            actions=[ActionType.SUSPEND_ACCOUNT],
            cooldown_seconds=300,
            metadata={"account_id": account_id} if account_id else {}
        )
        
        super().__init__(config)
        self.account_id = account_id
    
    def evaluate(self, context: RuleContext, metrics_collector: MetricsCollector) -> RuleResult:
        """Evaluate volume rule"""
        # Skip if specific account is configured and doesn't match
        if self.account_id and context.order and context.order.account_id != self.account_id:
            return RuleResult(triggered=False)
        
        return super().evaluate(context, metrics_collector)


class FrequencyRule(MetricBasedRule):
    """Specialized rule for frequency limits"""
    
    def __init__(self, rule_id: str, metric_type: MetricType = MetricType.ORDER_COUNT,
                 threshold: float = 50, window: Optional[TimeWindow] = None):
        # Create configuration
        if window is None:
            window = TimeWindow.seconds(1)
        
        metric_config = MetricConfig(
            metric_type=metric_type,
            threshold=threshold,
            window=window,
            dimensions=["account"]
        )
        
        config = RuleConfig(
            rule_id=rule_id,
            name=f"Frequency limit ({threshold}/{window.duration_seconds}s)",
            description=f"Suspend orders when rate exceeds {threshold} per {window.duration_seconds}s",
            metrics=[metric_config],
            actions=[ActionType.SUSPEND_ORDER],
            cooldown_seconds=60
        )
        
        super().__init__(config)


class CompositeRule(Rule):
    """Rule that combines multiple sub-rules"""
    
    def __init__(self, rule_id: str, name: str, rules: List[Rule], 
                 logic: str = "AND", description: str = ""):
        super().__init__(rule_id, name, description)
        self.rules = rules
        self.logic = logic.upper()  # AND or OR
    
    def evaluate(self, context: RuleContext, metrics_collector: MetricsCollector) -> RuleResult:
        """Evaluate composite rule"""
        if not self.enabled:
            return RuleResult(triggered=False)
        
        results = []
        all_metrics = {}
        all_events = []
        
        for rule in self.rules:
            if rule.enabled:
                result = rule.evaluate(context, metrics_collector)
                results.append(result)
                all_metrics.update(result.metrics)
                all_events.extend(result.events)
        
        # Apply logic
        if self.logic == "AND":
            triggered = all(r.triggered for r in results)
        else:  # OR
            triggered = any(r.triggered for r in results)
        
        if triggered:
            # Combine all actions
            all_actions = []
            reasons = []
            for result in results:
                if result.triggered:
                    all_actions.extend(result.actions)
                    if result.reason:
                        reasons.append(result.reason)
            
            return RuleResult(
                triggered=True,
                actions=all_actions,
                events=all_events,
                metrics=all_metrics,
                reason=f"{self.name}: {' AND '.join(reasons) if self.logic == 'AND' else ' OR '.join(reasons)}"
            )
        
        return RuleResult(
            triggered=False,
            metrics=all_metrics,
            events=all_events
        )


class RuleManager:
    """Manages all risk control rules"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.rules: Dict[str, Rule] = {}
        self._lock = threading.RLock()
        self._rule_stats = defaultdict(lambda: {"triggered": 0, "evaluated": 0})
    
    def add_rule(self, rule: Rule):
        """Add a rule to the manager"""
        with self._lock:
            self.rules[rule.rule_id] = rule
    
    def remove_rule(self, rule_id: str):
        """Remove a rule from the manager"""
        with self._lock:
            self.rules.pop(rule_id, None)
    
    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Get a rule by ID"""
        return self.rules.get(rule_id)
    
    def evaluate_all(self, context: RuleContext) -> List[RuleResult]:
        """Evaluate all rules and return results"""
        results = []
        
        with self._lock:
            # Sort rules by priority if they have it
            sorted_rules = sorted(
                self.rules.values(),
                key=lambda r: getattr(r, 'priority', 0),
                reverse=True
            )
        
        for rule in sorted_rules:
            if rule.enabled:
                result = rule.evaluate(context, self.metrics_collector)
                results.append(result)
                
                # Update statistics
                self._rule_stats[rule.rule_id]["evaluated"] += 1
                if result.triggered:
                    self._rule_stats[rule.rule_id]["triggered"] += 1
        
        return results
    
    def get_statistics(self) -> Dict[str, Dict[str, int]]:
        """Get rule evaluation statistics"""
        with self._lock:
            return dict(self._rule_stats)
    
    def load_from_config(self, config):
        """Load rules from configuration"""
        with self._lock:
            # Clear existing rules
            self.rules.clear()
            
            # Create rules from configuration
            for rule_config in config.rules:
                rule = MetricBasedRule(rule_config)
                self.add_rule(rule)