#!/usr/bin/env python3
"""
金融风控模块性能验证脚本
验证百万级/秒吞吐量和微秒级延迟
"""

import asyncio
import time
import random
import numpy as np
import argparse
import json
from datetime import datetime
from typing import List, Dict, Tuple
from collections import defaultdict
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

from risk_engine import RiskEngine
from risk_engine.async_engine import create_async_engine
from risk_engine.config import (
    RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig,
    StatsDimension
)
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType


class PerformanceValidator:
    """性能验证器"""
    
    def __init__(self, num_accounts: int = 100, num_contracts: int = 10):
        self.base_timestamp = int(time.time() * 1e9)
        self.num_accounts = num_accounts
        self.num_contracts = num_contracts
        
        # 生成测试数据
        self.accounts = [f"ACC_{i:04d}" for i in range(num_accounts)]
        self.contracts = {}
        
        # 创建合约映射
        products = ["T10Y", "T5Y", "IF", "IC", "IH"]
        for i in range(num_contracts):
            contract_id = f"C{i:04d}"
            self.contracts[contract_id] = {
                "product": products[i % len(products)],
                "exchange": "CFFEX",
                "base_price": 100.0 + i * 10
            }
    
    def create_config(self, enable_rules: bool = True) -> RiskEngineConfig:
        """创建引擎配置"""
        config_dict = {
            "contract_to_product": {k: v["product"] for k, v in self.contracts.items()},
            "contract_to_exchange": {k: v["exchange"] for k, v in self.contracts.items()},
            "num_shards": 128,
            "worker_threads": mp.cpu_count(),
            "max_queue_size": 1_000_000,
            "batch_size": 1000,
        }
        
        if enable_rules:
            config_dict.update({
                "volume_limit": VolumeLimitRuleConfig(
                    threshold=100000,  # 10万手
                    dimension=StatsDimension.PRODUCT,
                    metric=MetricType.TRADE_VOLUME
                ),
                "order_rate_limit": OrderRateLimitRuleConfig(
                    threshold=1000,  # 1000次/秒
                    window_seconds=1,
                    dimension=StatsDimension.ACCOUNT
                )
            })
        
        return RiskEngineConfig(**config_dict)
    
    def generate_orders(self, count: int) -> List[Order]:
        """批量生成订单"""
        orders = []
        for i in range(count):
            account = random.choice(self.accounts)
            contract = random.choice(list(self.contracts.keys()))
            contract_info = self.contracts[contract]
            
            order = Order(
                oid=i,
                account_id=account,
                contract_id=contract,
                direction=random.choice([Direction.BID, Direction.ASK]),
                price=contract_info["base_price"] * (1 + random.uniform(-0.01, 0.01)),
                volume=random.randint(1, 10),
                timestamp=self.base_timestamp + i
            )
            orders.append(order)
        
        return orders
    
    def generate_trades(self, orders: List[Order], fill_rate: float = 0.8) -> List[Trade]:
        """基于订单生成成交"""
        trades = []
        for i, order in enumerate(orders):
            if random.random() < fill_rate:
                trade = Trade(
                    tid=i,
                    oid=order.oid,
                    price=order.price,
                    volume=order.volume,
                    timestamp=order.timestamp + 1000,
                    account_id=order.account_id,
                    contract_id=order.contract_id
                )
                trades.append(trade)
        
        return trades
    
    def test_sync_performance(self, num_events: int = 100000) -> Dict:
        """测试同步引擎性能"""
        print(f"\n{'='*60}")
        print(f"测试同步引擎性能 (事件数: {num_events:,})")
        print(f"{'='*60}")
        
        config = self.create_config(enable_rules=True)
        engine = RiskEngine(config)
        
        # 准备测试数据
        orders = self.generate_orders(num_events // 2)
        trades = self.generate_trades(orders)
        
        # 测试订单处理
        order_latencies = []
        start_time = time.perf_counter()
        
        for order in orders:
            t1 = time.perf_counter_ns()
            engine.on_order(order)
            t2 = time.perf_counter_ns()
            order_latencies.append(t2 - t1)
        
        order_time = time.perf_counter() - start_time
        
        # 测试成交处理
        trade_latencies = []
        start_time = time.perf_counter()
        
        for trade in trades:
            t1 = time.perf_counter_ns()
            engine.on_trade(trade)
            t2 = time.perf_counter_ns()
            trade_latencies.append(t2 - t1)
        
        trade_time = time.perf_counter() - start_time
        
        # 计算统计
        total_events = len(orders) + len(trades)
        total_time = order_time + trade_time
        
        results = {
            "engine_type": "sync",
            "total_events": total_events,
            "orders_processed": len(orders),
            "trades_processed": len(trades),
            "total_time_seconds": total_time,
            "throughput_per_second": total_events / total_time,
            "order_latency_ns": {
                "mean": np.mean(order_latencies),
                "p50": np.percentile(order_latencies, 50),
                "p90": np.percentile(order_latencies, 90),
                "p99": np.percentile(order_latencies, 99),
                "p99.9": np.percentile(order_latencies, 99.9),
                "max": np.max(order_latencies)
            },
            "trade_latency_ns": {
                "mean": np.mean(trade_latencies),
                "p50": np.percentile(trade_latencies, 50),
                "p90": np.percentile(trade_latencies, 90),
                "p99": np.percentile(trade_latencies, 99),
                "p99.9": np.percentile(trade_latencies, 99.9),
                "max": np.max(trade_latencies)
            }
        }
        
        # 打印结果
        self._print_results(results)
        
        return results
    
    async def test_async_performance(self, num_events: int = 1000000) -> Dict:
        """测试异步引擎性能"""
        print(f"\n{'='*60}")
        print(f"测试异步引擎性能 (事件数: {num_events:,})")
        print(f"{'='*60}")
        
        config = self.create_config(enable_rules=True)
        engine = create_async_engine(config)
        
        await engine.start()
        
        try:
            # 准备测试数据
            orders = self.generate_orders(num_events // 2)
            trades = self.generate_trades(orders)
            
            # 测试并发提交
            start_time = time.perf_counter()
            
            # 批量提交订单
            order_tasks = []
            for order in orders:
                task = engine.submit_order(order)
                order_tasks.append(task)
            
            # 批量提交成交
            trade_tasks = []
            for trade in trades:
                task = engine.submit_trade(trade)
                trade_tasks.append(task)
            
            # 等待所有任务完成
            await asyncio.gather(*order_tasks, *trade_tasks)
            
            total_time = time.perf_counter() - start_time
            
            # 获取统计
            stats = engine.get_stats()
            
            results = {
                "engine_type": "async",
                "total_events": num_events,
                "orders_processed": stats.get("orders_processed", 0),
                "trades_processed": stats.get("trades_processed", 0),
                "total_time_seconds": total_time,
                "throughput_per_second": num_events / total_time,
                "actions_generated": stats.get("actions_generated", 0)
            }
            
            # 打印结果
            self._print_results(results)
            
            return results
            
        finally:
            await engine.stop()
    
    def test_latency_distribution(self, num_samples: int = 10000) -> Dict:
        """测试延迟分布"""
        print(f"\n{'='*60}")
        print(f"测试延迟分布 (样本数: {num_samples:,})")
        print(f"{'='*60}")
        
        config = self.create_config(enable_rules=True)
        engine = RiskEngine(config)
        
        # 预热
        for _ in range(1000):
            order = self.generate_orders(1)[0]
            engine.on_order(order)
        
        # 收集延迟数据
        latencies = defaultdict(list)
        
        for i in range(num_samples):
            order = self.generate_orders(1)[0]
            
            # 测试不同规则的延迟
            # 1. 小订单（不触发规则）
            order.volume = 1
            t1 = time.perf_counter_ns()
            engine.on_order(order)
            t2 = time.perf_counter_ns()
            latencies["small_order"].append(t2 - t1)
            
            # 2. 大订单（可能触发规则）
            order.volume = 1000
            order.oid = order.oid + 100000
            t1 = time.perf_counter_ns()
            engine.on_order(order)
            t2 = time.perf_counter_ns()
            latencies["large_order"].append(t2 - t1)
            
            # 3. 成交
            trade = Trade(
                tid=i,
                oid=order.oid,
                price=order.price,
                volume=1,
                timestamp=order.timestamp + 1000
            )
            t1 = time.perf_counter_ns()
            engine.on_trade(trade)
            t2 = time.perf_counter_ns()
            latencies["trade"].append(t2 - t1)
        
        # 计算统计
        results = {}
        for event_type, values in latencies.items():
            results[event_type] = {
                "count": len(values),
                "mean_ns": np.mean(values),
                "mean_us": np.mean(values) / 1000,
                "p50_us": np.percentile(values, 50) / 1000,
                "p90_us": np.percentile(values, 90) / 1000,
                "p99_us": np.percentile(values, 99) / 1000,
                "p99.9_us": np.percentile(values, 99.9) / 1000,
                "max_us": np.max(values) / 1000
            }
        
        # 打印结果
        print("\n延迟分布（微秒）:")
        print(f"{'事件类型':<15} {'平均':<10} {'P50':<10} {'P90':<10} {'P99':<10} {'P99.9':<10} {'最大':<10}")
        print("-" * 85)
        
        for event_type, stats in results.items():
            print(f"{event_type:<15} "
                  f"{stats['mean_us']:<10.2f} "
                  f"{stats['p50_us']:<10.2f} "
                  f"{stats['p90_us']:<10.2f} "
                  f"{stats['p99_us']:<10.2f} "
                  f"{stats['p99.9_us']:<10.2f} "
                  f"{stats['max_us']:<10.2f}")
        
        return results
    
    def test_concurrent_stress(self, duration_seconds: int = 60, target_tps: int = 1000000) -> Dict:
        """并发压力测试"""
        print(f"\n{'='*60}")
        print(f"并发压力测试")
        print(f"目标TPS: {target_tps:,}, 持续时间: {duration_seconds}秒")
        print(f"{'='*60}")
        
        config = self.create_config(enable_rules=True)
        engine = RiskEngine(config)
        
        # 计算每个线程的负载
        num_threads = mp.cpu_count()
        events_per_thread_per_second = target_tps // num_threads
        
        print(f"使用 {num_threads} 个线程，每线程 {events_per_thread_per_second:,} TPS")
        
        # 统计数据
        total_events = 0
        start_time = time.perf_counter()
        
        def worker(thread_id: int, stop_event):
            """工作线程"""
            local_count = 0
            orders = self.generate_orders(10000)  # 预生成订单
            order_idx = 0
            
            while not stop_event.is_set():
                order = orders[order_idx % len(orders)]
                order.oid = thread_id * 1000000 + local_count
                engine.on_order(order)
                
                local_count += 1
                order_idx += 1
                
                # 控制速率
                if local_count % 100 == 0:
                    elapsed = time.perf_counter() - start_time
                    if elapsed > 0:
                        current_tps = local_count / elapsed
                        if current_tps > events_per_thread_per_second:
                            time.sleep(0.001)
            
            return local_count
        
        # 启动工作线程
        stop_event = mp.Event()
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for i in range(num_threads):
                future = executor.submit(worker, i, stop_event)
                futures.append(future)
            
            # 运行指定时间
            time.sleep(duration_seconds)
            stop_event.set()
            
            # 收集结果
            for future in futures:
                total_events += future.result()
        
        total_time = time.perf_counter() - start_time
        actual_tps = total_events / total_time
        
        # 获取引擎统计
        stats = engine.get_stats()
        
        results = {
            "test_type": "concurrent_stress",
            "duration_seconds": duration_seconds,
            "target_tps": target_tps,
            "actual_tps": actual_tps,
            "total_events": total_events,
            "orders_processed": stats.get("orders_processed", 0),
            "actions_generated": stats.get("actions_generated", 0),
            "tps_achievement_rate": (actual_tps / target_tps) * 100
        }
        
        # 打印结果
        print(f"\n压力测试结果:")
        print(f"- 目标TPS: {target_tps:,}")
        print(f"- 实际TPS: {actual_tps:,.0f}")
        print(f"- 达成率: {results['tps_achievement_rate']:.1f}%")
        print(f"- 总事件数: {total_events:,}")
        print(f"- 触发动作: {stats.get('actions_generated', 0):,}")
        
        return results
    
    def _print_results(self, results: Dict):
        """打印性能测试结果"""
        print(f"\n性能测试结果:")
        print(f"- 引擎类型: {results.get('engine_type', 'N/A')}")
        print(f"- 总事件数: {results.get('total_events', 0):,}")
        print(f"- 处理时间: {results.get('total_time_seconds', 0):.3f}秒")
        print(f"- 吞吐量: {results.get('throughput_per_second', 0):,.0f} 事件/秒")
        
        if "order_latency_ns" in results:
            print(f"\n订单处理延迟（微秒）:")
            latency = results["order_latency_ns"]
            print(f"  - 平均: {latency['mean']/1000:.2f}")
            print(f"  - P50: {latency['p50']/1000:.2f}")
            print(f"  - P90: {latency['p90']/1000:.2f}")
            print(f"  - P99: {latency['p99']/1000:.2f}")
            print(f"  - P99.9: {latency['p99.9']/1000:.2f}")
            print(f"  - 最大: {latency['max']/1000:.2f}")
        
        if "trade_latency_ns" in results:
            print(f"\n成交处理延迟（微秒）:")
            latency = results["trade_latency_ns"]
            print(f"  - 平均: {latency['mean']/1000:.2f}")
            print(f"  - P50: {latency['p50']/1000:.2f}")
            print(f"  - P90: {latency['p90']/1000:.2f}")
            print(f"  - P99: {latency['p99']/1000:.2f}")
            print(f"  - P99.9: {latency['p99.9']/1000:.2f}")
            print(f"  - 最大: {latency['max']/1000:.2f}")
    
    def save_results(self, results: List[Dict], filename: str):
        """保存测试结果"""
        with open(filename, 'w') as f:
            json.dump({
                "test_time": datetime.now().isoformat(),
                "system_info": {
                    "cpu_count": mp.cpu_count(),
                },
                "results": results
            }, f, indent=2)
        print(f"\n结果已保存到: {filename}")


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="金融风控模块性能验证")
    parser.add_argument("--sync-events", type=int, default=100000,
                       help="同步测试事件数")
    parser.add_argument("--async-events", type=int, default=1000000,
                       help="异步测试事件数")
    parser.add_argument("--latency-samples", type=int, default=10000,
                       help="延迟测试样本数")
    parser.add_argument("--stress-duration", type=int, default=30,
                       help="压力测试持续时间（秒）")
    parser.add_argument("--target-tps", type=int, default=1000000,
                       help="目标TPS")
    parser.add_argument("--output", type=str, default="performance_results.json",
                       help="结果输出文件")
    
    args = parser.parse_args()
    
    print("="*60)
    print("金融风控模块性能验证")
    print("="*60)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"CPU核心数: {mp.cpu_count()}")
    
    validator = PerformanceValidator()
    results = []
    
    # 1. 同步引擎性能测试
    sync_result = validator.test_sync_performance(args.sync_events)
    results.append(sync_result)
    
    # 2. 异步引擎性能测试
    async_result = await validator.test_async_performance(args.async_events)
    results.append(async_result)
    
    # 3. 延迟分布测试
    latency_result = validator.test_latency_distribution(args.latency_samples)
    results.append({"test_type": "latency_distribution", "data": latency_result})
    
    # 4. 并发压力测试
    stress_result = validator.test_concurrent_stress(args.stress_duration, args.target_tps)
    results.append(stress_result)
    
    # 保存结果
    validator.save_results(results, args.output)
    
    # 总结
    print("\n" + "="*60)
    print("性能验证总结")
    print("="*60)
    
    print("\n✓ 吞吐量验证:")
    print(f"  - 同步引擎: {sync_result['throughput_per_second']:,.0f} 事件/秒")
    print(f"  - 异步引擎: {async_result['throughput_per_second']:,.0f} 事件/秒")
    if async_result['throughput_per_second'] >= 1000000:
        print("  ✓ 达到百万级/秒吞吐量目标")
    
    print("\n✓ 延迟验证:")
    if "order_latency_ns" in sync_result:
        p99_us = sync_result["order_latency_ns"]["p99"] / 1000
        print(f"  - P99延迟: {p99_us:.2f} 微秒")
        if p99_us < 1000:
            print("  ✓ 达到微秒级延迟目标")
    
    print("\n✓ 压力测试:")
    print(f"  - TPS达成率: {stress_result['tps_achievement_rate']:.1f}%")
    
    print("\n测试完成!")


if __name__ == "__main__":
    asyncio.run(main())