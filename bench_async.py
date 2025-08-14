"""
异步风控引擎性能基准测试。

目标：
- 验证百万级/秒事件处理能力
- 验证微秒级响应延迟
- 测试不同配置下的性能表现
"""

import asyncio
import time
import statistics
from typing import List, Dict
import random

from risk_engine.async_engine import create_async_engine, AsyncEngineConfig
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, StatsDimension
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType


class PerformanceBenchmark:
    """性能基准测试类。"""
    
    def __init__(self):
        """初始化基准测试。"""
        self.results: Dict[str, List[float]] = {}
        self.latencies: List[float] = []
        
    async def run_throughput_test(self, 
                                 num_events: int = 1_000_000,
                                 batch_size: int = 1000,
                                 num_workers: int = 8):
        """运行吞吐量测试。"""
        print(f"\n=== 吞吐量测试 ===")
        print(f"事件数量: {num_events:,}")
        print(f"批处理大小: {batch_size}")
        print(f"工作线程数: {num_workers}")
        
        # 创建引擎配置
        config = RiskEngineConfig(
            contract_to_product={"T2303": "T10Y", "T2306": "T10Y", "T2309": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX", "T2309": "CFFEX"},
            volume_limit=VolumeLimitRuleConfig(
                threshold=1000,
                dimension=StatsDimension.PRODUCT,
                metric=MetricType.TRADE_VOLUME
            ),
            order_rate_limit=OrderRateLimitRuleConfig(
                threshold=1000,
                window_seconds=1,
                dimension=StatsDimension.ACCOUNT
            ),
            num_shards=128,
            max_queue_size=1000000,
            batch_size=batch_size,
            worker_threads=num_workers,
        )
        
        async_config = AsyncEngineConfig(
            max_concurrent_tasks=10000,
            task_timeout_ms=50,
            batch_size=batch_size,
            num_workers=num_workers,
            enable_batching=True,
        )
        
        # 创建引擎
        engine = create_async_engine(config)
        engine.async_config = async_config
        
        # 启动引擎
        await engine.start()
        
        try:
            # 生成测试数据
            orders, trades = self._generate_test_data(num_events)
            
            # 预热
            print("预热中...")
            await self._warmup(engine, orders[:10000], trades[:2500])
            
            # 性能测试
            print("开始性能测试...")
            start_time = time.perf_counter()
            
            # 并发提交事件
            tasks = []
            for i in range(0, len(orders), batch_size):
                batch_orders = orders[i:i + batch_size]
                task = asyncio.create_task(
                    self._submit_orders_batch(engine, batch_orders)
                )
                tasks.append(task)
            
            for i in range(0, len(trades), batch_size):
                batch_trades = trades[i:i + batch_size]
                task = asyncio.create_task(
                    self._submit_trades_batch(engine, batch_trades)
                )
                tasks.append(task)
            
            # 等待所有任务完成
            await asyncio.gather(*tasks)
            
            end_time = time.perf_counter()
            
            # 等待队列处理完成
            await asyncio.sleep(2)
            
            # 计算性能指标
            total_time = end_time - start_time
            total_events = len(orders) + len(trades)
            throughput = total_events / total_time
            
            print(f"\n性能测试结果:")
            print(f"总时间: {total_time:.3f}秒")
            print(f"总事件数: {total_events:,}")
            print(f"吞吐量: {throughput:,.0f} 事件/秒")
            print(f"目标: 1,000,000 事件/秒")
            print(f"达成率: {throughput/1_000_000*100:.1f}%")
            
            # 获取引擎统计
            stats = engine.get_stats()
            print(f"\n引擎统计:")
            print(f"订单处理: {stats['orders_processed']:,}")
            print(f"成交处理: {stats['trades_processed']:,}")
            print(f"动作生成: {stats['actions_generated']:,}")
            print(f"平均延迟: {stats['avg_latency_ns']/1000:.2f} 微秒")
            print(f"最大延迟: {stats['max_latency_ns']/1000:.2f} 微秒")
            
            # 验证延迟要求
            max_latency_us = stats['max_latency_ns'] / 1000
            if max_latency_us <= 1000:  # 1毫秒 = 1000微秒
                print(f"✅ 延迟要求满足: {max_latency_us:.2f} 微秒 <= 1000 微秒")
            else:
                print(f"❌ 延迟要求未满足: {max_latency_us:.2f} 微秒 > 1000 微秒")
            
            # 验证吞吐量要求
            if throughput >= 1_000_000:
                print(f"✅ 吞吐量要求满足: {throughput:,.0f} 事件/秒 >= 1,000,000 事件/秒")
            else:
                print(f"❌ 吞吐量要求未满足: {throughput:,.0f} 事件/秒 < 1,000,000 事件/秒")
            
            self.results['throughput'] = [throughput]
            
        finally:
            await engine.stop()
    
    async def run_latency_test(self, num_events: int = 100_000):
        """运行延迟测试。"""
        print(f"\n=== 延迟测试 ===")
        print(f"事件数量: {num_events:,}")
        
        config = RiskEngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
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
            max_queue_size=100000,
            batch_size=100,
            worker_threads=4,
        )
        
        async_config = AsyncEngineConfig(
            max_concurrent_tasks=1000,
            task_timeout_ms=10,
            batch_size=100,
            num_workers=4,
            enable_batching=False,  # 关闭批处理以测试单事件延迟
        )
        
        engine = create_async_engine(config)
        engine.async_config = async_config
        
        await engine.start()
        
        try:
            orders, trades = self._generate_test_data(num_events)
            
            print("测试单事件延迟...")
            latencies = []
            
            # 测试订单延迟
            for i, order in enumerate(orders[:num_events//2]):
                start_time = time.perf_counter_ns()
                await engine.submit_order(order)
                # 等待处理完成
                await asyncio.sleep(0.000001)  # 1微秒
                end_time = time.perf_counter_ns()
                latency = end_time - start_time
                latencies.append(latency)
                
                if i % 10000 == 0:
                    print(f"已测试 {i} 个订单...")
            
            # 测试成交延迟
            for i, trade in enumerate(trades[:num_events//2]):
                start_time = time.perf_counter_ns()
                await engine.submit_trade(trade)
                await asyncio.sleep(0.000001)
                end_time = time.perf_counter_ns()
                latency = end_time - start_time
                latencies.append(latency)
                
                if i % 10000 == 0:
                    print(f"已测试 {i} 个成交...")
            
            # 等待处理完成
            await asyncio.sleep(2)
            
            # 计算延迟统计
            latencies_us = [l / 1000 for l in latencies]
            avg_latency = statistics.mean(latencies_us)
            p50_latency = statistics.median(latencies_us)
            p95_latency = sorted(latencies_us)[int(len(latencies_us) * 0.95)]
            p99_latency = sorted(latencies_us)[int(len(latencies_us) * 0.99)]
            max_latency = max(latencies_us)
            min_latency = min(latencies_us)
            
            print(f"\n延迟测试结果:")
            print(f"平均延迟: {avg_latency:.2f} 微秒")
            print(f"中位数延迟: {p50_latency:.2f} 微秒")
            print(f"P95延迟: {p95_latency:.2f} 微秒")
            print(f"P99延迟: {p99_latency:.2f} 微秒")
            print(f"最小延迟: {min_latency:.2f} 微秒")
            print(f"最大延迟: {max_latency:.2f} 微秒")
            
            # 验证微秒级延迟要求
            if p99_latency <= 1000:  # P99延迟 <= 1毫秒
                print(f"微秒级延迟要求满足: P99 {p99_latency:.2f} 微秒 <= 1000 微秒")
            else:
                print(f"微秒级延迟要求未满足: P99 {p99_latency:.2f} 微秒 > 1000 微秒")
            
            self.results['latency'] = latencies_us
            
        finally:
            await engine.stop()
    
    def _generate_test_data(self, num_events: int) -> tuple[List[Order], List[Trade]]:
        """生成测试数据。"""
        print(f"生成 {num_events:,} 个测试事件...")
        
        orders = []
        trades = []
        
        base_ts = int(time.time() * 1_000_000_000)  # 纳秒时间戳
        accounts = [f"ACC_{i:03d}" for i in range(100)]
        contracts = ["T2303", "T2306", "T2309"]
        directions = [Direction.BID, Direction.ASK]
        
        for i in range(num_events):
            # 生成订单
            order = Order(
                oid=i + 1,
                account_id=random.choice(accounts),
                contract_id=random.choice(contracts),
                direction=random.choice(directions),
                price=100.0 + random.uniform(-5.0, 5.0),
                volume=random.randint(1, 100),
                timestamp=base_ts + i * 1000,  # 每事件间隔1微秒
            )
            orders.append(order)
            
            # 每4个订单生成1个成交
            if i % 4 == 0:
                trade = Trade(
                    tid=i + 1,
                    oid=i + 1,
                    account_id=order.account_id,
                    contract_id=order.contract_id,
                    price=order.price,
                    volume=order.volume,
                    timestamp=base_ts + i * 1000 + 100,  # 成交时间稍晚
                )
                trades.append(trade)
        
        print(f"生成完成: {len(orders):,} 订单, {len(trades):,} 成交")
        return orders, trades
    
    async def _warmup(self, engine, orders: List[Order], trades: List[Trade]):
        """预热引擎。"""
        print("预热引擎...")
        
        # 提交预热数据
        for order in orders:
            await engine.submit_order(order)
        
        for trade in trades:
            await engine.submit_trade(trade)
        
        # 等待处理完成
        await asyncio.sleep(1)
        print("预热完成")
    
    async def _submit_orders_batch(self, engine, orders: List[Order]):
        """批量提交订单。"""
        for order in orders:
            await engine.submit_order(order)
    
    async def _submit_trades_batch(self, engine, trades: List[Trade]):
        """批量提交成交。"""
        for trade in trades:
            await engine.submit_trade(trade)
    
    def print_summary(self):
        """打印测试总结。"""
        print(f"\n=== 测试总结 ===")
        
        if 'throughput' in self.results:
            throughput = self.results['throughput'][0]
            print(f"吞吐量: {throughput:,.0f} 事件/秒")
            if throughput >= 1_000_000:
                print("高并发要求满足")
            else:
                print("高并发要求未满足")
        
        if 'latency' in self.results:
            latencies = self.results['latency']
            p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
            print(f"P99延迟: {p99_latency:.2f} 微秒")
            if p99_latency <= 1000:
                print("低延迟要求满足")
            else:
                print("低延迟要求未满足")


async def main():
    """主函数。"""
    print("异步风控引擎性能基准测试")
    print("=" * 50)
    
    benchmark = PerformanceBenchmark()
    
    # 运行吞吐量测试
    await benchmark.run_throughput_test(
        num_events=1_000_000,  # 100万事件
        batch_size=1000,
        num_workers=8
    )
    
    # 运行延迟测试
    await benchmark.run_latency_test(num_events=100_000)
    
    # 打印总结
    benchmark.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
