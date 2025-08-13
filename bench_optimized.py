#!/usr/bin/env python3
"""
高性能基准测试
分析性能瓶颈并测试优化效果
"""

import time
import cProfile
import pstats
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType

def null_sink(action, rule_id, obj):
    """空的动作处理器，避免IO开销"""
    pass

def bench_minimal(num_events: int = 500_000):
    """最小配置基准测试"""
    print(f"=== 最小配置测试 ({num_events} 事件) ===")
    
    # 最小配置：只有一个高阈值规则，几乎不会触发
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
            deduplicate_actions=False,  # 关闭去重以减少开销
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOL-HIGH", 
                metric=MetricType.TRADE_VOLUME, 
                threshold=1e9,  # 极高阈值，不会触发
                actions=(),  # 空动作
                by_account=True,
                by_product=False,  # 减少维度计算
            ),
        ],
        action_sink=null_sink,
    )
    
    base_ts = 2_000_000_000_000_000_000
    
    # 预生成所有事件对象，避免构造开销
    orders = []
    trades = []
    for i in range(num_events):
        orders.append(Order(i+1, "ACC_001", "T2303", Direction.BID, 100.0, 1, base_ts))
        if (i % 4) == 0:
            trades.append(Trade(tid=i+1, oid=i+1, account_id="ACC_001", contract_id="T2303", price=100.0, volume=1, timestamp=base_ts))
    
    print(f"预生成 {len(orders)} 订单 + {len(trades)} 成交")
    
    t0 = time.perf_counter()
    for order in orders:
        engine.on_order(order)
    for trade in trades:
        engine.on_trade(trade)
    t1 = time.perf_counter()
    
    dt = t1 - t0
    total_events = len(orders) + len(trades)
    throughput = total_events / dt
    print(f"处理完成: {dt:.3f}s => {throughput:.0f} evt/s")
    return throughput

def bench_realistic(num_events: int = 200_000):
    """现实配置基准测试"""
    print(f"\n=== 现实配置测试 ({num_events} 事件) ===")
    
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
            deduplicate_actions=True,
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOL-1000", metric=MetricType.TRADE_VOLUME, threshold=1000,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,), by_account=True, by_product=True,
            ),
            OrderRateLimitRule(
                rule_id="ORDER-50-1S", threshold=50, window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,), resume_actions=(Action.RESUME_ORDERING,),
            ),
        ],
        action_sink=null_sink,
    )
    
    base_ts = 2_000_000_000_000_000_000
    t0 = time.perf_counter()
    for i in range(num_events):
        ts = base_ts + i * 1000  # 微调时间戳
        engine.on_order(Order(i+1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts))
        if (i % 4) == 0:
            engine.on_trade(Trade(tid=i+1, oid=i+1, account_id="ACC_001", contract_id="T2303", price=100.0, volume=1, timestamp=ts))
    t1 = time.perf_counter()
    
    dt = t1 - t0
    total_events = num_events + num_events // 4
    throughput = total_events / dt
    print(f"处理完成: {dt:.3f}s => {throughput:.0f} evt/s")
    return throughput

def bench_with_profiling(num_events: int = 100_000):
    """带性能分析的基准测试"""
    print(f"\n=== 性能分析测试 ({num_events} 事件) ===")
    
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOL-1000", metric=MetricType.TRADE_VOLUME, threshold=1000,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,), by_account=True, by_product=True,
            ),
        ],
        action_sink=null_sink,
    )
    
    def run_test():
        base_ts = 2_000_000_000_000_000_000
        for i in range(num_events):
            ts = base_ts + i * 1000
            engine.on_order(Order(i+1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts))
            if (i % 4) == 0:
                engine.on_trade(Trade(tid=i+1, oid=i+1, account_id="ACC_001", contract_id="T2303", price=100.0, volume=1, timestamp=ts))
    
    # 性能分析
    profiler = cProfile.Profile()
    profiler.enable()
    run_test()
    profiler.disable()
    
    # 输出热点函数
    stats = pstats.Stats(profiler).sort_stats('cumulative')
    print("Top 10 热点函数:")
    stats.print_stats(10)

def main():
    print("金融风控引擎性能测试")
    print("目标: 1,000,000 evt/s (百万级/秒)")
    print("=" * 50)
    
    # 运行不同配置的测试
    minimal_throughput = bench_minimal(500_000)
    realistic_throughput = bench_realistic(200_000)
    
    print(f"\n=== 性能总结 ===")
    print(f"最小配置: {minimal_throughput:.0f} evt/s")
    print(f"现实配置: {realistic_throughput:.0f} evt/s") 
    print(f"目标达成度: {realistic_throughput/1_000_000*100:.1f}%")
    
    if realistic_throughput < 1_000_000:
        print("\n性能分析中...")
        bench_with_profiling(50_000)
        
    print("\n=== 优化建议 ===")
    print("1. 使用Cython/PyO3编译核心热点路径")
    print("2. 多进程分片架构 (按账户分片)")
    print("3. 使用原生扩展实现ShardedLockDict")
    print("4. NUMA亲和与CPU绑核")
    print("5. 零拷贝数据通道")

if __name__ == "__main__":
    main()