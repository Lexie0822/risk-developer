"""
Performance tests for the risk control system.
"""

import unittest
import time
import threading
import random
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.models import Order, Trade, Direction
from src.engine import RiskControlEngine
from src.metrics import MetricsCollector, TimeWindow


class TestPerformance(unittest.TestCase):
    """Performance tests to verify system meets requirements"""
    
    def setUp(self):
        """Set up test environment"""
        # Use more workers for performance tests
        self.engine = RiskControlEngine(num_workers=8)
        self.engine.start()
        time.sleep(0.1)  # Allow engine to start
    
    def tearDown(self):
        """Clean up after tests"""
        self.engine.stop()
    
    def test_order_processing_latency(self):
        """Test that order processing meets microsecond latency requirement"""
        latencies = []
        
        # Warm up
        for i in range(100):
            order = self._create_random_order(i)
            self.engine.process_order(order)
        
        # Measure latencies
        for i in range(1000):
            order = self._create_random_order(i + 100)
            
            start_time = time.perf_counter_ns()
            self.engine.process_order(order)
            end_time = time.perf_counter_ns()
            
            latency_us = (end_time - start_time) / 1000
            latencies.append(latency_us)
        
        # Calculate statistics
        avg_latency = statistics.mean(latencies)
        p50_latency = statistics.median(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
        p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
        
        print(f"\nOrder Processing Latency:")
        print(f"  Average: {avg_latency:.2f} µs")
        print(f"  P50: {p50_latency:.2f} µs")
        print(f"  P95: {p95_latency:.2f} µs")
        print(f"  P99: {p99_latency:.2f} µs")
        
        # Verify microsecond-level latency
        self.assertLess(p50_latency, 1000)  # P50 < 1ms
        self.assertLess(p95_latency, 5000)  # P95 < 5ms
        self.assertLess(p99_latency, 10000)  # P99 < 10ms
    
    def test_throughput_synchronous(self):
        """Test synchronous processing throughput"""
        num_orders = 10000
        start_time = time.perf_counter()
        
        for i in range(num_orders):
            order = self._create_random_order(i)
            self.engine.process_order(order)
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        throughput = num_orders / duration
        
        print(f"\nSynchronous Throughput:")
        print(f"  Processed: {num_orders} orders")
        print(f"  Duration: {duration:.2f} seconds")
        print(f"  Throughput: {throughput:.0f} orders/second")
        
        # Should handle at least 10K orders/second synchronously
        self.assertGreater(throughput, 10000)
    
    def test_throughput_asynchronous(self):
        """Test asynchronous processing throughput"""
        num_orders = 100000
        start_time = time.perf_counter()
        
        # Generate orders asynchronously
        for i in range(num_orders):
            order = self._create_random_order(i)
            self.engine.process_order_async(order)
        
        # Wait for processing to complete
        while True:
            stats = self.engine.get_statistics()
            if stats["engine"]["orders_processed"] >= num_orders * 0.99:  # 99% processed
                break
            time.sleep(0.1)
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        actual_processed = stats["engine"]["orders_processed"]
        throughput = actual_processed / duration
        
        print(f"\nAsynchronous Throughput:")
        print(f"  Processed: {actual_processed} orders")
        print(f"  Duration: {duration:.2f} seconds")
        print(f"  Throughput: {throughput:.0f} orders/second")
        
        # Should handle at least 100K orders/second asynchronously
        self.assertGreater(throughput, 100000)
    
    def test_concurrent_processing(self):
        """Test concurrent processing from multiple threads"""
        num_threads = 16
        orders_per_thread = 5000
        total_orders = num_threads * orders_per_thread
        
        def process_orders(thread_id):
            latencies = []
            for i in range(orders_per_thread):
                order = self._create_random_order(thread_id * orders_per_thread + i)
                
                start_time = time.perf_counter_ns()
                self.engine.process_order(order)
                end_time = time.perf_counter_ns()
                
                latency_us = (end_time - start_time) / 1000
                latencies.append(latency_us)
            
            return latencies
        
        start_time = time.perf_counter()
        
        # Process orders concurrently
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(process_orders, i) for i in range(num_threads)]
            all_latencies = []
            
            for future in as_completed(futures):
                all_latencies.extend(future.result())
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        throughput = total_orders / duration
        
        # Calculate latency statistics
        avg_latency = statistics.mean(all_latencies)
        p99_latency = statistics.quantiles(all_latencies, n=100)[98]
        
        print(f"\nConcurrent Processing:")
        print(f"  Threads: {num_threads}")
        print(f"  Total Orders: {total_orders}")
        print(f"  Duration: {duration:.2f} seconds")
        print(f"  Throughput: {throughput:.0f} orders/second")
        print(f"  Average Latency: {avg_latency:.2f} µs")
        print(f"  P99 Latency: {p99_latency:.2f} µs")
        
        # Should maintain high throughput under concurrent load
        self.assertGreater(throughput, 50000)
        self.assertLess(p99_latency, 10000)  # P99 < 10ms
    
    def test_mixed_workload(self):
        """Test performance with mixed orders and trades"""
        num_operations = 50000
        start_time = time.perf_counter()
        
        for i in range(num_operations):
            if i % 3 == 0:  # 33% trades
                trade = Trade(
                    tid=i,
                    oid=max(0, i - 10),  # Reference recent order
                    price=100.0 + random.random(),
                    volume=random.randint(1, 100),
                    timestamp=int(time.time() * 1e9) + i
                )
                self.engine.process_trade(trade)
            else:  # 67% orders
                order = self._create_random_order(i)
                self.engine.process_order(order)
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        throughput = num_operations / duration
        
        stats = self.engine.get_statistics()
        
        print(f"\nMixed Workload Performance:")
        print(f"  Total Operations: {num_operations}")
        print(f"  Orders Processed: {stats['engine']['orders_processed']}")
        print(f"  Trades Processed: {stats['engine']['trades_processed']}")
        print(f"  Duration: {duration:.2f} seconds")
        print(f"  Throughput: {throughput:.0f} ops/second")
        print(f"  Average Latency: {stats['engine']['avg_latency_us']:.2f} µs")
        
        # Should maintain performance with mixed workload
        self.assertGreater(throughput, 20000)
    
    def test_rule_evaluation_performance(self):
        """Test rule evaluation doesn't significantly impact performance"""
        # First, measure baseline without rules
        self.engine.rule_manager.rules.clear()
        
        baseline_latencies = []
        for i in range(1000):
            order = self._create_random_order(i)
            
            start_time = time.perf_counter_ns()
            self.engine.process_order(order)
            end_time = time.perf_counter_ns()
            
            latency_us = (end_time - start_time) / 1000
            baseline_latencies.append(latency_us)
        
        baseline_avg = statistics.mean(baseline_latencies)
        
        # Re-initialize engine with default rules
        self.engine.stop()
        self.engine = RiskControlEngine(num_workers=8)
        self.engine.start()
        time.sleep(0.1)
        
        # Measure with rules
        rule_latencies = []
        for i in range(1000):
            order = self._create_random_order(i + 1000)
            
            start_time = time.perf_counter_ns()
            self.engine.process_order(order)
            end_time = time.perf_counter_ns()
            
            latency_us = (end_time - start_time) / 1000
            rule_latencies.append(latency_us)
        
        rule_avg = statistics.mean(rule_latencies)
        overhead_percent = ((rule_avg - baseline_avg) / baseline_avg) * 100
        
        print(f"\nRule Evaluation Overhead:")
        print(f"  Baseline Latency: {baseline_avg:.2f} µs")
        print(f"  With Rules Latency: {rule_avg:.2f} µs")
        print(f"  Overhead: {overhead_percent:.1f}%")
        
        # Rule evaluation should add less than 50% overhead
        self.assertLess(overhead_percent, 50)
    
    def test_memory_stability(self):
        """Test memory stability under sustained load"""
        import gc
        import psutil
        import os
        
        process = psutil.Process(os.getpid())
        
        # Get initial memory usage
        gc.collect()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Process many orders
        for batch in range(10):
            for i in range(10000):
                order = self._create_random_order(batch * 10000 + i)
                self.engine.process_order(order)
                
                # Occasional trades
                if i % 10 == 0:
                    trade = Trade(
                        tid=batch * 10000 + i,
                        oid=batch * 10000 + i,
                        price=100.0,
                        volume=10,
                        timestamp=int(time.time() * 1e9) + i
                    )
                    self.engine.process_trade(trade)
            
            # Force cleanup
            current_time = int(time.time() * 1e9)
            self.engine.metrics_collector.engine.clear_expired(current_time)
            gc.collect()
        
        # Get final memory usage
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_growth = final_memory - initial_memory
        
        print(f"\nMemory Stability:")
        print(f"  Initial Memory: {initial_memory:.1f} MB")
        print(f"  Final Memory: {final_memory:.1f} MB")
        print(f"  Memory Growth: {memory_growth:.1f} MB")
        
        # Memory growth should be reasonable (less than 100MB)
        self.assertLess(memory_growth, 100)
    
    def test_metric_aggregation_performance(self):
        """Test performance of metric aggregation"""
        collector = MetricsCollector()
        
        # Generate many data points
        num_accounts = 100
        num_points_per_account = 1000
        
        start_time = time.perf_counter()
        current_timestamp = int(time.time() * 1e9)
        
        for account_idx in range(num_accounts):
            account_id = f"ACC_{account_idx:03d}"
            
            for i in range(num_points_per_account):
                # Create order
                order = Order(
                    oid=account_idx * num_points_per_account + i,
                    account_id=account_id,
                    contract_id=f"T230{account_idx % 10}",
                    direction=Direction.BID,
                    price=100.0,
                    volume=10,
                    timestamp=current_timestamp + i * 1000000  # 1ms apart
                )
                
                # Record metrics
                collector.record_order(order)
                
                # Simulate trade
                trade = Trade(
                    tid=order.oid,
                    oid=order.oid,
                    price=order.price,
                    volume=order.volume,
                    timestamp=order.timestamp + 500000  # 0.5ms later
                )
                trade.account_id = order.account_id
                trade.contract_id = order.contract_id
                
                collector.record_trade(trade, order)
        
        # Measure query performance
        query_start = time.perf_counter()
        
        for account_idx in range(num_accounts):
            account_id = f"ACC_{account_idx:03d}"
            
            # Query various metrics
            daily_volume = collector.get_account_volume(account_id, TimeWindow.days(1))
            order_rate = collector.get_account_order_rate(account_id, TimeWindow.seconds(1))
        
        query_end = time.perf_counter()
        
        total_points = num_accounts * num_points_per_account * 2  # orders + trades
        insertion_time = query_start - start_time
        query_time = query_end - query_start
        
        print(f"\nMetric Aggregation Performance:")
        print(f"  Total Data Points: {total_points}")
        print(f"  Insertion Time: {insertion_time:.2f} seconds")
        print(f"  Insertion Rate: {total_points/insertion_time:.0f} points/second")
        print(f"  Query Time: {query_time:.3f} seconds")
        print(f"  Queries: {num_accounts * 2}")
        print(f"  Query Rate: {num_accounts * 2 / query_time:.0f} queries/second")
        
        # Should handle high insertion and query rates
        self.assertGreater(total_points / insertion_time, 100000)  # >100K points/sec
        self.assertGreater(num_accounts * 2 / query_time, 1000)  # >1K queries/sec
    
    def _create_random_order(self, order_id):
        """Create a random order for testing"""
        accounts = [f"ACC_{i:03d}" for i in range(100)]
        contracts = ["T2303", "T2306", "T2309", "T2312", "IF2312", "IC2312", "IH2312"]
        
        return Order(
            oid=order_id,
            account_id=random.choice(accounts),
            contract_id=random.choice(contracts),
            direction=random.choice([Direction.BID, Direction.ASK]),
            price=100.0 + random.uniform(-5, 5),
            volume=random.randint(1, 100),
            timestamp=int(time.time() * 1e9) + order_id
        )


if __name__ == '__main__':
    # Run with verbosity to see print statements
    unittest.main(verbosity=2)