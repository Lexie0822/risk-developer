#!/usr/bin/env python3
"""
金融风控引擎完整示例

展示所有风控功能：
1. 单账户成交量限制
2. 报单频率控制
3. 多维统计（账户、产品、合约维度）
4. 动态规则调整
5. Action处理机制
"""

import time
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType
from risk_engine.stats import StatsDimension


class DemoActionHandler:
    """演示用的Action处理器"""
    
    def __init__(self):
        self.actions = []
        
    def __call__(self, action, rule_id, context):
        """处理Action"""
        self.actions.append({
            'action': action,
            'rule_id': rule_id,
            'context': context,
            'timestamp': time.time()
        })
        print(f"[ACTION] {action.name} triggered by rule '{rule_id}'")
        if hasattr(context, 'account_id'):
            print(f"         Account: {context.account_id}")
        if hasattr(context, 'contract_id'):
            print(f"         Contract: {context.contract_id}")


def demo_volume_limit():
    """演示成交量限制功能"""
    print("\n" + "="*60)
    print("演示1: 单账户成交量限制")
    print("="*60)
    
    handler = DemoActionHandler()
    
    # 创建引擎，设置成交量阈值为100手
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOLUME_LIMIT_100",
                metric=MetricType.TRADE_VOLUME,
                threshold=100,  # 100手限制
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True
            )
        ],
        action_sink=handler
    )
    
    base_ts = 1700000000000000000
    
    # 模拟交易：逐步接近并超过阈值
    print("\n模拟交易过程:")
    for i in range(12):
        order = Order(
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=base_ts + i * 1000000
        )
        engine.on_order(order)
        
        trade = Trade(
            tid=i+1,
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303",
            price=100.0,
            volume=10,
            timestamp=base_ts + i * 1000000 + 500
        )
        engine.on_trade(trade)
        
        total_volume = (i + 1) * 10
        print(f"Trade {i+1}: Volume=10, Total={total_volume}")
        
        if total_volume > 100 and len(handler.actions) > 0:
            print(">>> 成交量超过阈值，账户交易被暂停!")
            break


def demo_order_rate_limit():
    """演示报单频率控制"""
    print("\n" + "="*60)
    print("演示2: 报单频率控制")
    print("="*60)
    
    handler = DemoActionHandler()
    
    # 创建引擎，设置报单频率限制为5次/秒
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
        ),
        rules=[
            OrderRateLimitRule(
                rule_id="ORDER_RATE_5_PER_SEC",
                threshold=5,  # 5次/秒
                window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,),
                resume_actions=(Action.RESUME_ORDERING,)
            )
        ],
        action_sink=handler
    )
    
    base_ts = 1700000000000000000
    
    print("\n快速发送订单:")
    # 在同一秒内发送多个订单
    for i in range(8):
        order = Order(
            oid=i+1,
            account_id="ACC_001", 
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=base_ts + i * 100000000  # 100ms间隔
        )
        engine.on_order(order)
        print(f"Order {i+1} sent at {i*100}ms")
    
    print("\n等待1秒后继续发送:")
    # 1秒后继续发送，应该恢复
    for i in range(3):
        order = Order(
            oid=10+i,
            account_id="ACC_001",
            contract_id="T2303", 
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=base_ts + 2000000000 + i * 100000000  # 2秒后
        )
        engine.on_order(order)
        print(f"Order {10+i} sent at {2000+i*100}ms")


def demo_multi_dimension():
    """演示多维度统计"""
    print("\n" + "="*60)
    print("演示3: 多维度统计")
    print("="*60)
    
    handler = DemoActionHandler()
    
    # 创建引擎，同时支持账户维度和产品维度统计
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={
                "T2303": "T10Y",  # 10年国债
                "T2306": "T10Y",  # 10年国债
                "TF2303": "T5Y",  # 5年国债
            },
            contract_to_exchange={
                "T2303": "CFFEX",
                "T2306": "CFFEX", 
                "TF2303": "CFFEX"
            },
        ),
        rules=[
            # 账户维度：单账户总成交量不超过200手
            AccountTradeMetricLimitRule(
                rule_id="ACCOUNT_VOLUME_200",
                metric=MetricType.TRADE_VOLUME,
                threshold=200,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True,
                by_product=False
            ),
            # 产品维度：单产品总成交量不超过150手
            AccountTradeMetricLimitRule(
                rule_id="PRODUCT_VOLUME_150",
                metric=MetricType.TRADE_VOLUME,
                threshold=150,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True,
                by_product=True  # 产品维度
            )
        ],
        action_sink=handler
    )
    
    base_ts = 1700000000000000000
    
    print("\n模拟跨合约交易:")
    # 在不同合约上交易
    contracts = ["T2303", "T2306", "TF2303"]
    for i in range(18):
        contract = contracts[i % 3]
        
        order = Order(
            oid=i+1,
            account_id="ACC_001",
            contract_id=contract,
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=base_ts + i * 1000000
        )
        engine.on_order(order)
        
        trade = Trade(
            tid=i+1,
            oid=i+1,
            account_id="ACC_001",
            contract_id=contract,
            price=100.0,
            volume=10,
            timestamp=base_ts + i * 1000000 + 500
        )
        engine.on_trade(trade)
        
        print(f"Trade {i+1}: Contract={contract}, Volume=10")
        
        # 检查是否触发规则
        if len(handler.actions) > len(contracts):
            last_action = handler.actions[-1]
            print(f">>> 触发规则: {last_action['rule_id']}")


def demo_dynamic_adjustment():
    """演示动态调整规则"""
    print("\n" + "="*60)
    print("演示4: 动态调整规则阈值")
    print("="*60)
    
    handler = DemoActionHandler()
    
    # 创建引擎
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="DYNAMIC_VOLUME",
                metric=MetricType.TRADE_VOLUME,
                threshold=50,  # 初始阈值50手
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True
            ),
            OrderRateLimitRule(
                rule_id="DYNAMIC_RATE",
                threshold=3,  # 初始3次/秒
                window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,),
                resume_actions=(Action.RESUME_ORDERING,)
            )
        ],
        action_sink=handler
    )
    
    base_ts = 1700000000000000000
    
    print("\n初始阈值: 成交量50手, 报单频率3次/秒")
    
    # 发送一些交易
    for i in range(6):
        trade = Trade(
            tid=i+1,
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303",
            price=100.0,
            volume=10,
            timestamp=base_ts + i * 100000000
        )
        engine.on_trade(trade)
    
    print(f"已成交60手")
    
    # 动态调整阈值
    print("\n动态调整阈值: 成交量100手, 报单频率10次/秒")
    engine.update_volume_limit(threshold=100)
    engine.update_order_rate_limit(threshold=10, window_ns=1_000_000_000)
    
    # 继续交易
    for i in range(5):
        trade = Trade(
            tid=10+i,
            oid=10+i,
            account_id="ACC_001",
            contract_id="T2303",
            price=100.0,
            volume=10,
            timestamp=base_ts + 1000000000 + i * 100000000
        )
        engine.on_trade(trade)
    
    print(f"继续成交50手，总计110手")
    print(">>> 新阈值生效，110手触发限制!")


def demo_performance():
    """演示系统性能"""
    print("\n" + "="*60)
    print("演示5: 系统性能测试")
    print("="*60)
    
    # 空的action处理器（减少打印开销）
    def null_handler(action, rule_id, context):
        pass
    
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="PERF_VOL",
                metric=MetricType.TRADE_VOLUME,
                threshold=1000000,  # 设置很高避免触发
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True
            ),
            OrderRateLimitRule(
                rule_id="PERF_RATE",
                threshold=1000000,  # 设置很高避免触发
                window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,),
                resume_actions=(Action.RESUME_ORDERING,)
            )
        ],
        action_sink=null_handler
    )
    
    # 性能测试
    num_events = 100000
    base_ts = 1700000000000000000
    
    print(f"\n处理 {num_events} 个订单...")
    
    start_time = time.perf_counter()
    
    for i in range(num_events):
        order = Order(
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID if i % 2 == 0 else Direction.ASK,
            price=100.0 + (i % 10) * 0.1,
            volume=1 + (i % 5),
            timestamp=base_ts + i * 1000
        )
        engine.on_order(order)
        
        # 10%的订单产生成交
        if i % 10 == 0:
            trade = Trade(
                tid=i//10+1,
                oid=i+1,
                account_id="ACC_001",
                contract_id="T2303",
                price=order.price,
                volume=order.volume,
                timestamp=order.timestamp + 500
            )
            engine.on_trade(trade)
    
    end_time = time.perf_counter()
    duration = end_time - start_time
    
    total_events = num_events + num_events // 10
    throughput = total_events / duration
    avg_latency_us = (duration / total_events) * 1_000_000
    
    print(f"\n性能统计:")
    print(f"  处理事件数: {total_events} (订单: {num_events}, 成交: {num_events//10})")
    print(f"  总耗时: {duration:.3f} 秒")
    print(f"  吞吐量: {throughput:,.0f} ops/秒")
    print(f"  平均延迟: {avg_latency_us:.2f} 微秒")


def main():
    """运行所有演示"""
    print("金融风控引擎功能演示")
    print("=" * 60)
    
    demos = [
        ("成交量限制", demo_volume_limit),
        ("报单频率控制", demo_order_rate_limit),
        ("多维度统计", demo_multi_dimension),
        ("动态规则调整", demo_dynamic_adjustment),
        ("性能测试", demo_performance)
    ]
    
    for name, func in demos:
        input(f"\n按Enter键继续: {name}...")
        func()
    
    print("\n" + "="*60)
    print("演示完成!")


if __name__ == "__main__":
    main()