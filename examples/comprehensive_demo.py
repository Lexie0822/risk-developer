#!/usr/bin/env python3
"""
金融风控引擎综合演示：高频交易场景的实时风控
"""

import time
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Cancel, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType


def current_ns() -> int:
    """获取当前纳秒时间戳"""
    return time.time_ns()


def demo_multi_dimensional_limits():
    """演示多维度限制规则"""
    print("=== 多维度限制规则演示 ===")
    
    # 配置合约到产品映射
    contract_to_product = {
        "T2303": "T10Y",  # 10年期国债期货
        "T2306": "T10Y",
        "TF2303": "TF5Y",  # 5年期国债期货
        "TF2306": "TF5Y",
    }
    
    contract_to_exchange = {
        "T2303": "CFFEX", "T2306": "CFFEX",
        "TF2303": "CFFEX", "TF2306": "CFFEX",
    }
    
    def action_handler(action, rule_id, obj):
        print(f"🚨 触发动作: {action.name} (规则: {rule_id}) -> {type(obj).__name__} {getattr(obj, 'account_id', 'N/A')}")
    
    engine = RiskEngine(
        EngineConfig(
            contract_to_product=contract_to_product,
            contract_to_exchange=contract_to_exchange,
        ),
        rules=[
            # 1. 账户维度：单账户日成交量限制
            AccountTradeMetricLimitRule(
                rule_id="ACCOUNT_VOLUME_LIMIT",
                metric=MetricType.TRADE_VOLUME,
                threshold=1000,  # 1000手
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True,
                by_product=False,
                by_contract=False,
            ),
            # 2. 产品维度：单产品日成交量限制
            AccountTradeMetricLimitRule(
                rule_id="PRODUCT_VOLUME_LIMIT", 
                metric=MetricType.TRADE_VOLUME,
                threshold=500,  # 500手
                actions=(Action.ALERT,),
                by_account=True,
                by_product=True,
                by_contract=False,
            ),
            # 3. 成交金额限制
            AccountTradeMetricLimitRule(
                rule_id="NOTIONAL_LIMIT",
                metric=MetricType.TRADE_NOTIONAL,
                threshold=1_000_000,  # 100万元
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True,
            ),
            # 4. 撤单量限制
            AccountTradeMetricLimitRule(
                rule_id="CANCEL_LIMIT",
                metric=MetricType.CANCEL_COUNT,
                threshold=100,  # 100次撤单
                actions=(Action.BLOCK_CANCEL,),
                by_account=True,
            ),
            # 5. 报单频率控制
            OrderRateLimitRule(
                rule_id="ORDER_RATE_LIMIT",
                threshold=10,  # 10次/秒
                window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,),
                resume_actions=(Action.RESUME_ORDERING,),
            ),
        ],
        action_sink=action_handler,
    )
    
    base_ts = current_ns()
    account = "DEMO_001"
    
    print("\n1. 正常交易 - 不触发任何限制")
    # 小额交易，不会触发限制
    engine.on_order(Order(1, account, "T2303", Direction.BID, 100.0, 10, base_ts))
    engine.on_trade(Trade(1, 1, 100.0, 10, base_ts + 1000, account, "T2303"))
    
    print("\n2. 产品维度成交量接近限制")
    # 在不同合约上交易，但同一产品
    for i in range(2, 10):
        contract = "T2303" if i % 2 == 0 else "T2306"
        engine.on_trade(Trade(i, i, 100.0, 50, base_ts + i * 1000, account, contract))
    
    print("\n3. 高频下单触发频率控制")
    # 快速下单触发频率限制
    for i in range(10, 22):
        engine.on_order(Order(i, account, "T2303", Direction.BID, 100.0, 1, base_ts + i * 100_000))
    
    print("\n4. 大额交易触发成交金额限制")
    # 大额交易
    engine.on_trade(Trade(100, 100, 10000.0, 100, base_ts + 20_000_000, account, "T2303"))
    
    print("\n5. 频繁撤单")
    # 大量撤单
    for i in range(200, 305):
        engine.on_cancel(Cancel(i, i-100, account, "T2303", base_ts + i * 1000))


def demo_product_aggregation():
    """演示产品维度聚合"""
    print("\n=== 产品维度聚合演示 ===")
    
    contract_to_product = {"T2303": "BOND_10Y", "T2306": "BOND_10Y", "T2309": "BOND_10Y"}
    
    def action_handler(action, rule_id, obj):
        print(f"📊 产品聚合触发: {action.name} (规则: {rule_id})")
    
    engine = RiskEngine(
        EngineConfig(contract_to_product=contract_to_product),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="PRODUCT_AGG_DEMO",
                metric=MetricType.TRADE_VOLUME,
                threshold=200,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True,
                by_product=True,
            ),
        ],
        action_sink=action_handler,
    )
    
    base_ts = current_ns()
    account = "AGG_DEMO"
    
    print("在不同合约交易，但聚合到同一产品:")
    
    # 在三个不同合约上分别交易，累计达到阈值
    trades = [
        ("T2303", 80),
        ("T2306", 70), 
        ("T2309", 60),  # 总计210 > 200，应触发
    ]
    
    for i, (contract, volume) in enumerate(trades, 1):
        print(f"  合约 {contract}: {volume}手")
        engine.on_trade(Trade(i, i, 100.0, volume, base_ts + i * 1000, account, contract))


def demo_extensibility():
    """演示系统扩展性"""
    print("\n=== 扩展性演示 ===")
    
    # 自定义风控规则
    class CustomOrderPatternRule:
        """自定义规则：检测异常下单模式"""
        def __init__(self, rule_id: str):
            self.rule_id = rule_id
            self._order_history = {}
        
        def on_order(self, ctx, order):
            # 检测是否有异常的价格跳跃
            key = f"{order.account_id}:{order.contract_id}"
            if key in self._order_history:
                last_price = self._order_history[key]
                price_change = abs(order.price - last_price) / last_price
                if price_change > 0.1:  # 价格变化超过10%
                    from risk_engine.rules import RuleResult
                    return RuleResult(
                        actions=[Action.BLOCK_ORDER],
                        reasons=[f"价格异常跳跃: {price_change:.2%}"]
                    )
            self._order_history[key] = order.price
            return None
            
        def on_trade(self, ctx, trade):
            return None
            
        def on_cancel(self, ctx, cancel):
            return None
    
    def action_handler(action, rule_id, obj):
        print(f"🔧 自定义规则触发: {action.name} (规则: {rule_id})")
    
    engine = RiskEngine(
        EngineConfig(),
        rules=[CustomOrderPatternRule("CUSTOM_PATTERN")],
        action_sink=action_handler,
    )
    
    base_ts = current_ns()
    account = "CUSTOM_USER"
    
    print("正常价格下单:")
    engine.on_order(Order(1, account, "TEST001", Direction.BID, 100.0, 10, base_ts))
    
    print("异常价格跳跃:")
    engine.on_order(Order(2, account, "TEST001", Direction.BID, 120.0, 10, base_ts + 1000))


def demo_performance():
    """演示性能特性"""
    print("\n=== 性能演示 ===")
    
    engine = RiskEngine(
        EngineConfig(contract_to_product={"PERF001": "TEST"}),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="PERF_TEST",
                metric=MetricType.TRADE_VOLUME,
                threshold=100000,  # 高阈值，避免在性能测试中触发
                actions=(Action.ALERT,),
                by_account=True,
            ),
        ],
    )
    
    # 模拟高频场景
    n_events = 10000
    start_time = time.time()
    base_ts = current_ns()
    
    for i in range(n_events):
        if i % 2 == 0:
            engine.on_order(Order(i, f"PERF_{i%100}", "PERF001", Direction.BID, 100.0, 1, base_ts + i))
        else:
            engine.on_trade(Trade(i, i-1, 100.0, 1, base_ts + i, f"PERF_{i%100}", "PERF001"))
    
    elapsed = time.time() - start_time
    throughput = n_events / elapsed
    
    print(f"处理 {n_events} 个事件用时: {elapsed:.3f}秒")
    print(f"吞吐量: {throughput:,.0f} 事件/秒")
    print(f"平均延迟: {elapsed/n_events*1000:.2f} 毫秒/事件")


if __name__ == "__main__":
    print("🏦 金融风控引擎综合演示")
    print("=" * 50)
    
    demo_multi_dimensional_limits()
    demo_product_aggregation() 
    demo_extensibility()
    demo_performance()
    
    print("\n✅ 演示完成！")
    print("\n💡 关键特性:")
    print("  - 多维度统计 (账户/合约/产品/交易所/账户组)")
    print("  - 多种指标 (成交量/成交金额/报单量/撤单量)")
    print("  - 动态规则配置")
    print("  - 高并发优化 (分片锁/无锁读取)")
    print("  - 微秒级延迟目标")
    print("  - 可扩展架构")