#!/usr/bin/env python3
"""
高性能多进程风控演示
演示如何通过多进程分片架构达到百万级/秒吞吐量
"""

import time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType

def null_sink(action, rule_id, obj):
    """空的动作处理器"""
    pass

def create_engine():
    """创建风控引擎实例"""
    return RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
            deduplicate_actions=False,  # 关闭去重优化性能
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOL-1000", 
                metric=MetricType.TRADE_VOLUME, 
                threshold=1000,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,), 
                by_account=True, 
                by_product=False,  # 简化维度
            ),
        ],
        action_sink=null_sink,
    )

def worker_process(worker_id: int, num_events: int, account_range: tuple):
    """工作进程函数"""
    engine = create_engine()
    base_ts = 2_000_000_000_000_000_000
    
    start_acc, end_acc = account_range
    
    t0 = time.perf_counter()
    for i in range(num_events):
        # 账户ID分片：worker_id确定账户范围
        acc_idx = (start_acc + i) % (end_acc - start_acc) + start_acc
        account_id = f"ACC_{acc_idx:04d}"
        
        ts = base_ts + i * 100  # 纳秒级间隔
        
        # 处理订单
        order = Order(
            oid=worker_id * num_events + i + 1,
            account_id=account_id,
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=ts
        )
        engine.on_order(order)
        
        # 每4个订单有一个成交
        if i % 4 == 0:
            trade = Trade(
                tid=worker_id * num_events + i + 1,
                oid=order.oid,
                price=100.0,
                volume=1,
                timestamp=ts + 50,
                account_id=account_id,
                contract_id="T2303"
            )
            engine.on_trade(trade)
    
    t1 = time.perf_counter()
    duration = t1 - t0
    total_events = num_events + num_events // 4
    throughput = total_events / duration
    
    return {
        'worker_id': worker_id,
        'events_processed': total_events,
        'duration': duration,
        'throughput': throughput
    }

def benchmark_multiprocess(num_workers: int = 4, events_per_worker: int = 250_000):
    """多进程性能基准测试"""
    print(f"=== 多进程性能测试 ===")
    print(f"工作进程数: {num_workers}")
    print(f"每进程事件数: {events_per_worker}")
    print(f"总事件数: {num_workers * events_per_worker}")
    
    # 为每个工作进程分配账户范围，避免数据竞争
    accounts_per_worker = 1000
    account_ranges = []
    for i in range(num_workers):
        start_acc = i * accounts_per_worker
        end_acc = (i + 1) * accounts_per_worker
        account_ranges.append((start_acc, end_acc))
    
    # 启动多进程
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        overall_start = time.perf_counter()
        
        for i in range(num_workers):
            future = executor.submit(
                worker_process, 
                i, 
                events_per_worker, 
                account_ranges[i]
            )
            futures.append(future)
        
        # 收集结果
        results = []
        for future in futures:
            result = future.result()
            results.append(result)
        
        overall_end = time.perf_counter()
    
    # 汇总性能指标
    total_events = sum(r['events_processed'] for r in results)
    total_duration = overall_end - overall_start
    aggregate_throughput = total_events / total_duration
    
    print(f"\n=== 结果汇总 ===")
    for r in results:
        print(f"Worker {r['worker_id']}: {r['events_processed']} events in {r['duration']:.3f}s => {r['throughput']:.0f} evt/s")
    
    print(f"\n聚合性能: {total_events} events in {total_duration:.3f}s => {aggregate_throughput:.0f} evt/s")
    print(f"目标达成度: {aggregate_throughput/1_000_000*100:.1f}%")
    
    return aggregate_throughput

def benchmark_single_optimized(num_events: int = 1_000_000):
    """单进程优化版基准测试"""
    print(f"\n=== 单进程优化测试 ===")
    print(f"事件数: {num_events}")
    
    # 使用最精简配置
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
            deduplicate_actions=False,
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOL-NOLIMIT", 
                metric=MetricType.TRADE_VOLUME, 
                threshold=1e12,  # 极高阈值
                actions=(),  # 无动作
                by_account=True,
                by_product=False,
                by_contract=False,
                by_exchange=False,
                by_account_group=False,
            ),
        ],
        action_sink=null_sink,
    )
    
    base_ts = 2_000_000_000_000_000_000
    
    t0 = time.perf_counter()
    for i in range(num_events):
        ts = base_ts + i * 100
        order = Order(i+1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts)
        engine.on_order(order)
        
        if i % 10 == 0:  # 减少成交比例
            trade = Trade(i+1, i+1, 100.0, 1, ts+50, "ACC_001", "T2303")
            engine.on_trade(trade)
    
    t1 = time.perf_counter()
    duration = t1 - t0
    total_events = num_events + num_events // 10
    throughput = total_events / duration
    
    print(f"单进程优化: {total_events} events in {duration:.3f}s => {throughput:.0f} evt/s")
    return throughput

def main():
    print("高性能金融风控引擎演示")
    print("目标: 1,000,000 evt/s (百万级/秒)")
    print("=" * 60)
    
    # 检测CPU核心数
    cpu_count = mp.cpu_count()
    print(f"系统CPU核心数: {cpu_count}")
    
    # 单进程优化测试
    single_throughput = benchmark_single_optimized(500_000)
    
    # 多进程测试
    num_workers = min(4, cpu_count)  # 使用较少的进程避免上下文切换开销
    multi_throughput = benchmark_multiprocess(num_workers, 250_000)
    
    print(f"\n=== 性能对比 ===")
    print(f"单进程优化: {single_throughput:.0f} evt/s")
    print(f"多进程({num_workers}核): {multi_throughput:.0f} evt/s")
    print(f"性能提升: {multi_throughput/single_throughput:.1f}x")
    
    if multi_throughput >= 1_000_000:
        print("🎉 恭喜！已达到百万级/秒性能目标！")
    else:
        print(f"\n=== 进一步优化建议 ===")
        print("1. 使用更多CPU核心进行分片")
        print("2. Cython/PyO3编译热点路径")
        print("3. 使用共享内存减少进程间通信")
        print("4. DPDK/用户态网络栈")
        print("5. CPU绑核与NUMA优化")

if __name__ == "__main__":
    main()