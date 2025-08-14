"""
金融风控模块基本使用示例。

展示系统的核心功能：
1. 基本风控引擎使用
2. 异步高性能引擎使用
3. 自定义规则开发
4. 动态配置更新
"""

import asyncio
import time
from typing import Optional

from risk_engine import RiskEngine, EngineConfig
from risk_engine.async_engine import create_async_engine, AsyncEngineConfig
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, StatsDimension
from risk_engine.models import Order, Trade, Direction
from risk_engine.actions import Action
from risk_engine.metrics import MetricType
from risk_engine.rules import Rule, RuleContext, RuleResult


def basic_sync_engine_example():
    """基本同步风控引擎使用示例。"""
    print("\n=== 基本同步风控引擎示例 ===")
    
    # 创建引擎配置
    config = EngineConfig(
        contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
        deduplicate_actions=True,
    )
    
    # 创建风控引擎
    engine = RiskEngine(config)
    
    # 添加默认规则
    from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
    
    # 成交量限制规则
    volume_rule = AccountTradeMetricLimitRule(
        rule_id="VOLUME-LIMIT",
        metric=MetricType.TRADE_VOLUME,
        threshold=1000,  # 1000手
        actions=(Action.SUSPEND_ACCOUNT_TRADING,),
        by_account=True,
        by_product=True,
    )
    
    # 报单频率限制规则
    rate_rule = OrderRateLimitRule(
        rule_id="RATE-LIMIT",
        threshold=50,  # 50次/秒
        window_seconds=1,
        suspend_actions=(Action.SUSPEND_ORDERING,),
        resume_actions=(Action.RESUME_ORDERING,),
        dimension="account",
    )
    
    engine.add_rule(volume_rule)
    engine.add_rule(rate_rule)
    
    # 模拟订单和成交数据
    base_ts = int(time.time() * 1_000_000_000)
    
    print("处理订单...")
    for i in range(100):
        order = Order(
            oid=i + 1,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0 + i * 0.01,
            volume=10,
            timestamp=base_ts + i * 1000,
        )
        engine.on_order(order)
    
    print("处理成交...")
    for i in range(25):
        trade = Trade(
            tid=i + 1,
            oid=i + 1,
            account_id="ACC_001",
            contract_id="T2303",
            price=100.0 + i * 0.01,
            volume=10,
            timestamp=base_ts + i * 1000 + 100,
        )
        engine.on_trade(trade)
    
    print("基本示例完成")


async def async_engine_example():
    """异步高性能风控引擎使用示例。"""
    print("\n=== 异步高性能风控引擎示例 ===")
    
    # 创建异步引擎配置
    config = RiskEngineConfig(
        contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
        volume_limit=VolumeLimitRuleConfig(
            threshold=1000,
            dimension=StatsDimension.PRODUCT,
            metric=MetricType.TRADE_VOLUME
        ),
        order_rate_limit=OrderRateLimitRuleConfig(
            threshold=100,
            window_seconds=1,
            dimension=StatsDimension.ACCOUNT
        ),
        num_shards=64,
        worker_threads=4,
    )
    
    async_config = AsyncEngineConfig(
        max_concurrent_tasks=1000,
        task_timeout_ms=50,
        batch_size=100,
        num_workers=4,
        enable_batching=True,
    )
    
    # 创建异步引擎
    engine = create_async_engine(config)
    engine.async_config = async_config
    
    # 启动引擎
    await engine.start()
    
    try:
        print("异步引擎已启动，开始处理事件...")
        
        # 生成测试数据
        base_ts = int(time.time() * 1_000_000_000)
        
        # 并发提交订单
        order_tasks = []
        for i in range(1000):
            order = Order(
                oid=i + 1,
                account_id=f"ACC_{i % 10:03d}",
                contract_id="T2303",
                direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                price=100.0 + (i % 100) * 0.01,
                volume=random.randint(1, 100),
                timestamp=base_ts + i * 1000,
            )
            task = asyncio.create_task(engine.submit_order(order))
            order_tasks.append(task)
        
        # 并发提交成交
        trade_tasks = []
        for i in range(250):
            trade = Trade(
                tid=i + 1,
                oid=i + 1,
                account_id=f"ACC_{i % 10:03d}",
                contract_id="T2303",
                price=100.0 + (i % 100) * 0.01,
                volume=random.randint(1, 100),
                timestamp=base_ts + i * 1000 + 100,
            )
            task = asyncio.create_task(engine.submit_trade(trade))
            trade_tasks.append(task)
        
        # 等待所有任务完成
        await asyncio.gather(*order_tasks + trade_tasks)
        
        # 等待处理完成
        await asyncio.sleep(2)
        
        # 获取性能统计
        stats = engine.get_stats()
        print(f"\n异步引擎性能统计:")
        print(f"订单处理: {stats['orders_processed']:,}")
        print(f"成交处理: {stats['trades_processed']:,}")
        print(f"动作生成: {stats['actions_generated']:,}")
        print(f"平均延迟: {stats['avg_latency_ns']/1000:.2f} 微秒")
        print(f"最大延迟: {stats['max_latency_ns']/1000:.2f} 微秒")
        
    finally:
        await engine.stop()
        print("异步引擎已停止")


def custom_rule_example():
    """自定义规则开发示例。"""
    print("\n=== 自定义规则开发示例 ===")
    
    # 自定义风控规则：价格偏离监控
    class PriceDeviationRule(Rule):
        def __init__(self, rule_id: str, max_deviation: float, base_price: float):
            self.rule_id = rule_id
            self.max_deviation = max_deviation
            self.base_price = base_price
        
        def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
            deviation = abs(order.price - self.base_price) / self.base_price
            if deviation > self.max_deviation:
                return RuleResult(
                    actions=[Action.BLOCK_ORDER],
                    reasons=[f"价格偏离过大: {deviation:.2%} > {self.max_deviation:.2%}"]
                )
            return None
        
        def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
            deviation = abs(trade.price - self.base_price) / self.base_price
            if deviation > self.max_deviation:
                return RuleResult(
                    actions=[Action.ALERT],
                    reasons=[f"成交价格偏离过大: {deviation:.2%} > {self.max_deviation:.2%}"]
                )
            return None
    
    # 创建引擎并添加自定义规则
    config = EngineConfig(contract_to_product={"T2303": "T10Y"})
    engine = RiskEngine(config)
    
    # 添加自定义规则
    price_rule = PriceDeviationRule(
        rule_id="PRICE-DEVIATION",
        max_deviation=0.05,  # 5%
        base_price=100.0
    )
    engine.add_rule(price_rule)
    
    # 测试自定义规则
    base_ts = int(time.time() * 1_000_000_000)
    
    # 正常价格订单
    normal_order = Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 10, base_ts)
    result = engine.on_order(normal_order)
    print(f"正常价格订单结果: {result}")
    
    # 异常价格订单
    abnormal_order = Order(2, "ACC_001", "T2303", Direction.BID, 110.0, 10, base_ts)
    result = engine.on_order(abnormal_order)
    print(f"异常价格订单结果: {result}")
    
    print("自定义规则示例完成")


def dynamic_config_example():
    """动态配置更新示例。"""
    print("\n=== 动态配置更新示例 ===")
    
    # 创建引擎
    config = EngineConfig(contract_to_product={"T2303": "T10Y"})
    engine = RiskEngine(config)
    
    # 添加初始规则
    from risk_engine.rules import AccountTradeMetricLimitRule
    from risk_engine.stats import StatsDimension
    
    volume_rule = AccountTradeMetricLimitRule(
        rule_id="VOLUME-LIMIT",
        metric=MetricType.TRADE_VOLUME,
        threshold=1000,
        actions=(Action.SUSPEND_ACCOUNT_TRADING,),
        by_account=True,
        by_product=True,
    )
    engine.add_rule(volume_rule)
    
    print("初始配置: 成交量阈值 1000 手")
    
    # 动态更新配置
    print("更新配置: 成交量阈值调整为 2000 手")
    engine.update_volume_limit(threshold=2000, dimension=StatsDimension.PRODUCT)
    
    # 测试更新后的配置
    base_ts = int(time.time() * 1_000_000_000)
    
    # 提交大量成交，测试新阈值
    for i in range(1500):
        trade = Trade(
            tid=i + 1,
            oid=i + 1,
            account_id="ACC_001",
            contract_id="T2303",
            price=100.0,
            volume=1,
            timestamp=base_ts + i * 1000,
        )
        result = engine.on_trade(trade)
        if result and result.actions:
            print(f"触发风控动作: {result.actions}, 原因: {result.reasons}")
            break
    
    print("动态配置更新示例完成")


async def main():
    """主函数。"""
    print("金融风控模块使用示例")
    print("=" * 50)
    
    # 运行各种示例
    basic_sync_engine_example()
    await async_engine_example()
    custom_rule_example()
    dynamic_config_example()
    
    print("\n所有示例运行完成！")


if __name__ == "__main__":
    # 添加随机数生成
    import random
    random.seed(42)
    
    # 运行示例
    asyncio.run(main())