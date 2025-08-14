#!/usr/bin/env python3
"""
金融风控模块扩展点演示

展示系统的扩展性：
1. 新增统计维度
2. 新增指标类型
3. 新增规则类型
4. 动态配置更新
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from risk_engine import RiskEngine, EngineConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.actions import Action
from risk_engine.rules import Rule, RuleContext, RuleResult
from risk_engine.metrics import MetricType
from risk_engine.dimensions import make_dimension_key


def demo_new_dimension():
    """演示新增统计维度"""
    print("\n=== 新增统计维度演示 ===")
    
    # 1. 定义新的维度枚举
    class ExtendedDimension(str):
        """扩展的统计维度"""
        ACCOUNT = "account"
        CONTRACT = "contract"
        PRODUCT = "product"
        EXCHANGE = "exchange"
        ACCOUNT_GROUP = "account_group"
        # 新增维度：交易策略
        STRATEGY = "strategy"
        # 新增维度：风险等级
        RISK_LEVEL = "risk_level"
    
    # 2. 扩展维度键生成函数
    def make_extended_dimension_key(
        account_id: Optional[str] = None,
        contract_id: Optional[str] = None,
        product_id: Optional[str] = None,
        exchange_id: Optional[str] = None,
        account_group_id: Optional[str] = None,
        strategy: Optional[str] = None,      # 新增：交易策略
        risk_level: Optional[str] = None,   # 新增：风险等级
    ) -> tuple:
        """生成扩展的维度键"""
        key_parts = []
        
        if account_id:
            key_parts.append(f"account:{account_id}")
        if contract_id:
            key_parts.append(f"contract:{contract_id}")
        if product_id:
            key_parts.append(f"product:{product_id}")
        if exchange_id:
            key_parts.append(f"exchange:{exchange_id}")
        if account_group_id:
            key_parts.append(f"account_group:{account_group_id}")
        if strategy:  # 新增维度
            key_parts.append(f"strategy:{strategy}")
        if risk_level:  # 新增维度
            key_parts.append(f"risk_level:{risk_level}")
        
        return tuple(key_parts)
    
    # 3. 演示新维度的使用
    print("原始维度键:")
    original_key = make_dimension_key(
        account_id="ACC_001",
        contract_id="T2303",
        product_id="T10Y"
    )
    print(f"  {original_key}")
    
    print("\n扩展维度键:")
    extended_key = make_extended_dimension_key(
        account_id="ACC_001",
        contract_id="T2303",
        product_id="T10Y",
        strategy="ARBITRAGE",      # 新增：套利策略
        risk_level="HIGH"          # 新增：高风险等级
    )
    print(f"  {extended_key}")
    
    print("✅ 新增统计维度演示完成")


def demo_new_metric():
    """演示新增指标类型"""
    print("\n=== 新增指标类型演示 ===")
    
    # 1. 扩展指标类型枚举
    class ExtendedMetricType(str):
        """扩展的指标类型"""
        # 原有指标
        TRADE_VOLUME = "trade_volume"
        TRADE_NOTIONAL = "trade_notional"
        ORDER_COUNT = "order_count"
        
        # 新增指标：撤单率
        CANCEL_RATE = "cancel_rate"
        # 新增指标：成交率
        FILL_RATE = "fill_rate"
        # 新增指标：价格偏离度
        PRICE_DEVIATION = "price_deviation"
        # 新增指标：波动率
        VOLATILITY = "volatility"
    
    # 2. 指标计算器
    class MetricCalculator:
        """指标计算器"""
        
        @staticmethod
        def calculate_cancel_rate(total_orders: int, cancelled_orders: int) -> float:
            """计算撤单率"""
            if total_orders == 0:
                return 0.0
            return cancelled_orders / total_orders
        
        @staticmethod
        def calculate_fill_rate(total_orders: int, filled_orders: int) -> float:
            """计算成交率"""
            if total_orders == 0:
                return 0.0
            return filled_orders / total_orders
        
        @staticmethod
        def calculate_price_deviation(price: float, reference_price: float) -> float:
            """计算价格偏离度"""
            if reference_price == 0:
                return 0.0
            return abs(price - reference_price) / reference_price
        
        @staticmethod
        def calculate_volatility(prices: List[float]) -> float:
            """计算价格波动率"""
            if len(prices) < 2:
                return 0.0
            
            # 计算价格变化率的标准差
            returns = []
            for i in range(1, len(prices)):
                if prices[i-1] != 0:
                    returns.append((prices[i] - prices[i-1]) / prices[i-1])
            
            if not returns:
                return 0.0
            
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            return variance ** 0.5
    
    # 3. 演示新指标的计算
    calculator = MetricCalculator()
    
    print("撤单率计算:")
    cancel_rate = calculator.calculate_cancel_rate(100, 20)
    print(f"  总订单: 100, 撤单: 20, 撤单率: {cancel_rate:.2%}")
    
    print("\n成交率计算:")
    fill_rate = calculator.calculate_fill_rate(100, 80)
    print(f"  总订单: 100, 成交: 80, 成交率: {fill_rate:.2%}")
    
    print("\n价格偏离度计算:")
    deviation = calculator.calculate_price_deviation(105.0, 100.0)
    print(f"  当前价格: 105.0, 参考价格: 100.0, 偏离度: {deviation:.2%}")
    
    print("\n波动率计算:")
    prices = [100.0, 101.0, 99.0, 102.0, 98.0]
    volatility = calculator.calculate_volatility(prices)
    print(f"  价格序列: {prices}, 波动率: {volatility:.4f}")
    
    print("✅ 新增指标类型演示完成")


def demo_new_rule():
    """演示新增规则类型"""
    print("\n=== 新增规则类型演示 ===")
    
    # 1. 价格偏离度监控规则
    class PriceDeviationRule(Rule):
        """价格偏离度监控规则"""
        
        def __init__(self, rule_id: str, max_deviation: float, reference_price: float):
            self.rule_id = rule_id
            self.max_deviation = max_deviation
            self.reference_price = reference_price
        
        def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
            """监控订单价格偏离度"""
            deviation = abs(order.price - self.reference_price) / self.reference_price
            
            if deviation > self.max_deviation:
                return RuleResult(
                    actions=[Action.ALERT],
                    reasons=[f"订单价格偏离度 {deviation:.2%} 超过阈值 {self.max_deviation:.2%}"]
                )
            return None
        
        def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
            """监控成交价格偏离度"""
            deviation = abs(trade.price - self.reference_price) / self.reference_price
            
            if deviation > self.max_deviation:
                return RuleResult(
                    actions=[Action.ALERT],
                    reasons=[f"成交价格偏离度 {deviation:.2%} 超过阈值 {self.max_deviation:.2%}"]
                )
            return None
    
    # 2. 撤单率监控规则
    class CancelRateRule(Rule):
        """撤单率监控规则"""
        
        def __init__(self, rule_id: str, max_cancel_rate: float):
            self.rule_id = rule_id
            self.max_cancel_rate = max_cancel_rate
            self.order_counts = {}  # account_id -> (total, cancelled)
        
        def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
            """记录订单"""
            if order.account_id not in self.order_counts:
                self.order_counts[order.account_id] = (0, 0)
            
            total, cancelled = self.order_counts[order.account_id]
            self.order_counts[order.account_id] = (total + 1, cancelled)
            return None
        
        def on_cancel(self, account_id: str) -> Optional[RuleResult]:
            """记录撤单（模拟）"""
            if account_id in self.order_counts:
                total, cancelled = self.order_counts[account_id]
                self.order_counts[account_id] = (total, cancelled + 1)
                
                # 计算撤单率
                cancel_rate = cancelled / total if total > 0 else 0.0
                
                if cancel_rate > self.max_cancel_rate:
                    return RuleResult(
                        actions=[Action.SUSPEND_ORDERING],
                        reasons=[f"撤单率 {cancel_rate:.2%} 超过阈值 {self.max_cancel_rate:.2%}"]
                    )
            return None
    
    # 3. 演示新规则的使用
    print("创建价格偏离度监控规则:")
    price_rule = PriceDeviationRule(
        rule_id="PRICE-DEVIATION",
        max_deviation=0.05,  # 5%阈值
        reference_price=100.0
    )
    print(f"  规则ID: {price_rule.rule_id}")
    print(f"  最大偏离度: {price_rule.max_deviation:.1%}")
    print(f"  参考价格: {price_rule.reference_price}")
    
    print("\n创建撤单率监控规则:")
    cancel_rule = CancelRateRule(
        rule_id="CANCEL-RATE",
        max_cancel_rate=0.3  # 30%阈值
    )
    print(f"  规则ID: {cancel_rule.rule_id}")
    print(f"  最大撤单率: {cancel_rule.max_cancel_rate:.1%}")
    
    print("✅ 新增规则类型演示完成")


def demo_dynamic_config():
    """演示动态配置更新"""
    print("\n=== 动态配置更新演示 ===")
    
    # 1. 创建基础引擎
    config = EngineConfig(
        contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
        deduplicate_actions=True,
    )
    
    engine = RiskEngine(config)
    
    # 2. 添加基础规则
    from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
    
    volume_rule = AccountTradeMetricLimitRule(
        rule_id="VOLUME-LIMIT",
        metric=MetricType.TRADE_VOLUME,
        threshold=1000,
        actions=(Action.SUSPEND_ACCOUNT_TRADING,),
        by_account=True,
        by_product=True,
    )
    
    rate_rule = OrderRateLimitRule(
        rule_id="RATE-LIMIT",
        threshold=50,
        window_seconds=1,
        suspend_actions=(Action.SUSPEND_ORDERING,),
        resume_actions=(Action.RESUME_ORDERING,),
        dimension="account",
    )
    
    engine.add_rule(volume_rule)
    engine.add_rule(rate_rule)
    
    print("初始配置:")
    print(f"  成交量阈值: 1000手")
    print(f"  报单频率阈值: 50次/秒")
    
    # 3. 动态更新配置
    print("\n动态更新配置:")
    
    # 更新成交量阈值
    engine.update_volume_limit(threshold=2000)
    print(f"  成交量阈值更新为: 2000手")
    
    # 更新报单频率阈值
    engine.update_order_rate_limit(threshold=100)
    print(f"  报单频率阈值更新为: 100次/秒")
    
    # 4. 运行时规则替换
    print("\n运行时规则替换:")
    
    # 创建新的成交量规则
    new_volume_rule = AccountTradeMetricLimitRule(
        rule_id="VOLUME-LIMIT-V2",
        metric=MetricType.TRADE_VOLUME,
        threshold=3000,
        actions=(Action.SUSPEND_ACCOUNT_TRADING, Action.ALERT),
        by_account=True,
        by_product=True,
    )
    
    # 替换规则
    engine.update_rules([new_volume_rule, rate_rule])
    print(f"  成交量阈值更新为: 3000手")
    print(f"  新增告警动作")
    
    print("✅ 动态配置更新演示完成")


def demo_plugin_architecture():
    """演示插件化架构"""
    print("\n=== 插件化架构演示 ===")
    
    # 1. 规则插件接口
    class RulePlugin:
        """规则插件基类"""
        
        def __init__(self, plugin_id: str, version: str):
            self.plugin_id = plugin_id
            self.version = version
        
        def get_rules(self) -> List[Rule]:
            """获取插件提供的规则"""
            raise NotImplementedError
        
        def get_config_schema(self) -> Dict[str, Any]:
            """获取插件配置模式"""
            raise NotImplementedError
    
    # 2. 具体插件实现
    class MarketMakingPlugin(RulePlugin):
        """做市商风控插件"""
        
        def __init__(self):
            super().__init__("market_making", "1.0.0")
        
        def get_rules(self) -> List[Rule]:
            """获取做市商风控规则"""
            rules = []
            
            # 做市商报价价差监控
            class SpreadMonitorRule(Rule):
                def __init__(self):
                    self.rule_id = "SPREAD-MONITOR"
                
                def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
                    # 简化的价差监控逻辑
                    if order.direction == Direction.BID and order.price > 100.0:
                        return RuleResult(
                            actions=[Action.ALERT],
                            reasons=["做市商买价过高"]
                        )
                    return None
            
            rules.append(SpreadMonitorRule())
            return rules
        
        def get_config_schema(self) -> Dict[str, Any]:
            return {
                "max_spread": {"type": "float", "default": 0.01, "description": "最大价差"},
                "min_quote_size": {"type": "int", "default": 100, "description": "最小报价量"}
            }
    
    class ArbitragePlugin(RulePlugin):
        """套利风控插件"""
        
        def __init__(self):
            super().__init__("arbitrage", "1.0.0")
        
        def get_rules(self) -> List[Rule]:
            """获取套利风控规则"""
            rules = []
            
            # 套利机会监控
            class ArbitrageMonitorRule(Rule):
                def __init__(self):
                    self.rule_id = "ARBITRAGE-MONITOR"
                
                def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
                    # 简化的套利监控逻辑
                    if trade.volume > 1000:
                        return RuleResult(
                            actions=[Action.ALERT],
                            reasons=["大额套利交易"]
                        )
                    return None
            
            rules.append(ArbitrageMonitorRule())
            return rules
        
        def get_config_schema(self) -> Dict[str, Any]:
            return {
                "max_position": {"type": "int", "default": 10000, "description": "最大持仓"},
                "max_trade_size": {"type": "int", "default": 1000, "description": "最大交易量"}
            }
    
    # 3. 插件管理器
    class PluginManager:
        """插件管理器"""
        
        def __init__(self):
            self.plugins: Dict[str, RulePlugin] = {}
        
        def register_plugin(self, plugin: RulePlugin):
            """注册插件"""
            self.plugins[plugin.plugin_id] = plugin
            print(f"  注册插件: {plugin.plugin_id} v{plugin.version}")
        
        def get_all_rules(self) -> List[Rule]:
            """获取所有插件的规则"""
            all_rules = []
            for plugin in self.plugins.values():
                all_rules.extend(plugin.get_rules())
            return all_rules
        
        def get_plugin_configs(self) -> Dict[str, Dict[str, Any]]:
            """获取所有插件的配置模式"""
            configs = {}
            for plugin_id, plugin in self.plugins.items():
                configs[plugin_id] = plugin.get_config_schema()
            return configs
    
    # 4. 演示插件系统
    print("创建插件管理器:")
    plugin_manager = PluginManager()
    
    print("\n注册做市商插件:")
    market_making_plugin = MarketMakingPlugin()
    plugin_manager.register_plugin(market_making_plugin)
    
    print("\n注册套利插件:")
    arbitrage_plugin = ArbitragePlugin()
    plugin_manager.register_plugin(arbitrage_plugin)
    
    print("\n获取所有插件规则:")
    all_rules = plugin_manager.get_all_rules()
    for rule in all_rules:
        print(f"  - {rule.rule_id}")
    
    print("\n获取插件配置模式:")
    configs = plugin_manager.get_plugin_configs()
    for plugin_id, schema in configs.items():
        print(f"  {plugin_id}:")
        for param, config in schema.items():
            print(f"    {param}: {config['type']} (默认: {config['default']})")
    
    print("✅ 插件化架构演示完成")


def main():
    """主函数"""
    print("🚀 金融风控模块扩展点演示")
    print("=" * 50)
    
    # 运行所有演示
    demo_new_dimension()
    demo_new_metric()
    demo_new_rule()
    demo_dynamic_config()
    demo_plugin_architecture()
    
    print("\n" + "=" * 50)
    print("🎉 所有扩展点演示完成！")
    print("\n系统扩展性总结:")
    print("✅ 支持新增统计维度（策略、风险等级等）")
    print("✅ 支持新增指标类型（撤单率、成交率、波动率等）")
    print("✅ 支持新增规则类型（价格偏离度、撤单率监控等）")
    print("✅ 支持动态配置更新和热更新")
    print("✅ 支持插件化架构，便于功能扩展")


if __name__ == "__main__":
    main()