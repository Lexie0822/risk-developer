#!/usr/bin/env python3
"""
Simple demonstration of the Financial Risk Control System
"""

import sys
import os
import time

# Add parent directory to path to allow absolute imports
sys.path.insert(0, os.path.dirname(__file__))

# Import from src package
import json
from src.models import Order, Trade, Direction, ActionType
from src.engine import RiskControlEngine
from src.config import ConfigManager, RiskControlConfig, RuleConfig, MetricConfig
from src.metrics import MetricType, TimeWindow


def demo_basic_functionality():
    """Demonstrate basic system functionality"""
    print("=" * 60)
    print("金融风控系统演示 - Basic Functionality Demo")
    print("=" * 60)
    
    # Create engine with default config
    print("\n1. 初始化风控引擎...")
    engine = RiskControlEngine(num_workers=2)
    engine.start()
    print("   ✓ 引擎启动成功")
    
    # Register action handlers
    print("\n2. 注册Action处理器...")
    
    def handle_action(action):
        print(f"   [ACTION] {action.action_type.name}: {action.account_id} - {action.reason}")
    
    for action_type in ActionType:
        engine.register_action_handler(action_type, handle_action)
    print("   ✓ 处理器注册完成")
    
    # Process normal orders
    print("\n3. 处理正常订单...")
    current_time = int(time.time() * 1e9)
    
    for i in range(5):
        order = Order(
            oid=i,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0 + i * 0.1,
            volume=50,
            timestamp=current_time + i * 1e9
        )
        
        actions = engine.process_order(order)
        print(f"   Order {i}: 处理完成，生成 {len(actions)} 个actions")
        
        # Simulate trade
        trade = Trade(
            tid=i,
            oid=i,
            price=order.price,
            volume=order.volume,
            timestamp=order.timestamp + 5e8
        )
        
        trade_actions = engine.process_trade(trade)
        if trade_actions:
            print(f"   Trade {i}: 触发 {len(trade_actions)} 个actions")
    
    # Show statistics
    print("\n4. 系统统计信息...")
    stats = engine.get_statistics()
    print(f"   处理订单数: {stats['engine']['orders_processed']}")
    print(f"   处理成交数: {stats['engine']['trades_processed']}")
    print(f"   平均延迟: {stats['engine']['avg_latency_us']:.2f} μs")
    print(f"   吞吐量: {stats['engine']['throughput_ops_per_sec']:.0f} ops/s")
    
    engine.stop()
    print("\n✓ 演示完成")


def demo_volume_limit():
    """Demonstrate volume limit rule"""
    print("\n" + "=" * 60)
    print("金融风控系统演示 - Volume Limit Demo")
    print("=" * 60)
    
    engine = RiskControlEngine()
    engine.start()
    
    # Register handlers
    triggered = False
    def handle_suspend(action):
        nonlocal triggered
        triggered = True
        print(f"\n   🚨 风控触发: {action.reason}")
    
    engine.register_action_handler(ActionType.SUSPEND_ACCOUNT, handle_suspend)
    
    print("\n模拟大额成交，触发日成交量限制...")
    current_time = int(time.time() * 1e9)
    
    # Generate trades that will exceed limit
    for i in range(12):  # 12 * 100 = 1200 > 1000 limit
        order = Order(
            oid=i,
            account_id="ACC_TRADER_001",
            contract_id="IF2312",
            direction=Direction.BID,
            price=4000.0,
            volume=100,
            timestamp=current_time + i * 1e8
        )
        
        engine.process_order(order)
        
        trade = Trade(
            tid=i,
            oid=i,
            price=4000.0,
            volume=100,
            timestamp=order.timestamp + 5e7
        )
        
        engine.process_trade(trade)
        
        metrics = engine.get_account_metrics("ACC_TRADER_001")
        print(f"   交易 {i+1}: 累计成交量 = {metrics['daily_volume']} 手", end="")
        
        if triggered:
            print(" ← 触发风控!")
            break
        else:
            print()
    
    engine.stop()
    print("\n✓ 成交量限制演示完成")


def demo_frequency_control():
    """Demonstrate frequency control"""
    print("\n" + "=" * 60)
    print("金融风控系统演示 - Frequency Control Demo")
    print("=" * 60)
    
    engine = RiskControlEngine()
    engine.start()
    
    # Register handler
    triggered = False
    def handle_suspend_order(action):
        nonlocal triggered
        triggered = True
        print(f"\n   🚨 频率控制触发: {action.reason}")
    
    engine.register_action_handler(ActionType.SUSPEND_ORDER, handle_suspend_order)
    
    print("\n模拟高频报单...")
    current_time = int(time.time() * 1e9)
    
    # Submit orders rapidly
    for i in range(100):
        order = Order(
            oid=i,
            account_id="ACC_HFT_001",
            contract_id="IC2312",
            direction=Direction.BID if i % 2 == 0 else Direction.ASK,
            price=6000.0 + (i % 10) * 0.2,
            volume=1,
            timestamp=current_time + i * 5e6  # 5ms apart = 200/sec
        )
        
        actions = engine.process_order(order)
        
        if i % 10 == 0:
            metrics = engine.get_account_metrics("ACC_HFT_001")
            print(f"   订单 {i}: 报单频率 = {metrics['order_rate_per_sec']:.0f} 次/秒")
        
        if triggered:
            print(f"   在第 {i} 个订单时触发频率限制")
            break
    
    engine.stop()
    print("\n✓ 频率控制演示完成")


def demo_performance():
    """Demonstrate system performance"""
    print("\n" + "=" * 60)
    print("金融风控系统演示 - Performance Demo")
    print("=" * 60)
    
    engine = RiskControlEngine(num_workers=4)
    engine.start()
    
    print("\n测试系统性能...")
    
    # Warm up
    print("   预热中...")
    current_time = int(time.time() * 1e9)
    for i in range(100):
        order = Order(
            oid=i,
            account_id=f"ACC_{i % 10}",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=current_time + i * 1e6
        )
        engine.process_order(order)
    
    # Performance test
    print("   性能测试中...")
    num_orders = 10000
    start_time = time.perf_counter()
    
    for i in range(num_orders):
        order = Order(
            oid=100 + i,
            account_id=f"ACC_{i % 100}",
            contract_id=f"T230{i % 10}",
            direction=Direction.BID if i % 2 == 0 else Direction.ASK,
            price=100.0 + (i % 10) * 0.1,
            volume=10 + (i % 50),
            timestamp=current_time + i * 1e6
        )
        engine.process_order(order)
    
    end_time = time.perf_counter()
    duration = end_time - start_time
    throughput = num_orders / duration
    
    print(f"\n   性能测试结果:")
    print(f"   - 处理订单数: {num_orders}")
    print(f"   - 总耗时: {duration:.2f} 秒")
    print(f"   - 吞吐量: {throughput:.0f} 订单/秒")
    
    stats = engine.get_statistics()
    print(f"   - 平均延迟: {stats['engine']['avg_latency_us']:.2f} μs")
    print(f"   - 最大延迟: {stats['engine']['max_latency_us']:.2f} μs")
    
    engine.stop()
    print("\n✓ 性能测试完成")


if __name__ == "__main__":
    print("\n🚀 金融风控系统演示程序\n")
    
    demos = [
        ("基础功能", demo_basic_functionality),
        ("成交量限制", demo_volume_limit),
        ("频率控制", demo_frequency_control),
        ("性能测试", demo_performance)
    ]
    
    for i, (name, func) in enumerate(demos, 1):
        print(f"\n--- Demo {i}: {name} ---")
        try:
            func()
        except Exception as e:
            print(f"\n❌ 演示出错: {e}")
        
        if i < len(demos):
            time.sleep(1)
    
    print("\n" + "=" * 60)
    print("✅ 所有演示完成!")
    print("=" * 60)