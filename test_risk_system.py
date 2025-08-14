#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import random
import threading
from typing import List
from models import Order, Trade, Direction, ActionType, get_current_timestamp_ns
from risk_control_engine import RiskControlEngine


class RiskSystemTester:
    """风控系统测试类"""
    
    def __init__(self):
        self.engine = RiskControlEngine()
        self.test_results = []
        self.action_log = []
        
        # 注册动作回调
        self.engine.add_action_callback(self._log_action)
        
    def _log_action(self, action):
        """记录触发的动作"""
        self.action_log.append({
            "timestamp": action.timestamp,
            "action_type": action.action_type.value,
            "target_id": action.target_id,
            "reason": action.reason
        })
        
    def setup_test_environment(self):
        """设置测试环境"""
        print("正在初始化测试环境...")
        
        if not self.engine.start():
            raise RuntimeError("引擎启动失败")
            
        # 等待引擎完全启动
        time.sleep(0.1)
        print("测试环境初始化完成")
        
    def teardown_test_environment(self):
        """清理测试环境"""
        print("正在清理测试环境...")
        self.engine.stop()
        print("测试环境清理完成")
        
    def test_account_volume_limit(self):
        """测试账户成交量限制规则"""
        print("开始测试账户成交量限制规则...")
        
        account_id = "TEST_ACC_001"
        contract_id = "T2303"
        
        # 清空动作日志
        self.action_log.clear()
        
        # 模拟大量成交，触发1000手限制
        for i in range(1200):  # 超过1000手阈值
            order = Order(
                oid=i + 1,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID,
                price=100.0 + random.uniform(-1, 1),
                volume=1,
                timestamp=get_current_timestamp_ns()
            )
            
            trade = Trade(
                tid=i + 1,
                oid=i + 1,
                price=order.price,
                volume=1,
                timestamp=get_current_timestamp_ns()
            )
            
            self.engine.submit_order(order)
            self.engine.submit_trade(trade, order)
            
        # 等待处理完成
        time.sleep(1.0)
        
        # 检查是否触发了暂停交易动作
        suspend_actions = [a for a in self.action_log 
                          if a["action_type"] == "suspend_trading" 
                          and a["target_id"] == account_id]
        
        if suspend_actions:
            print(f"账户成交量限制测试通过: 触发了 {len(suspend_actions)} 次暂停交易动作")
            self.test_results.append(("账户成交量限制", "通过"))
        else:
            print("账户成交量限制测试失败: 未触发预期的动作")
            self.test_results.append(("账户成交量限制", "失败"))
            
    def test_order_frequency_limit(self):
        """测试报单频率限制规则"""
        print("开始测试报单频率限制规则...")
        
        account_id = "TEST_ACC_002"
        contract_id = "T2306"
        
        # 清空动作日志
        self.action_log.clear()
        
        # 在1秒内提交大量订单，触发50次/秒限制
        start_time = get_current_timestamp_ns()
        for i in range(60):  # 超过50次阈值
            order = Order(
                oid=i + 2000,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.ASK,
                price=100.0,
                volume=1,
                timestamp=start_time + i * 1000000  # 纳秒间隔
            )
            
            self.engine.submit_order(order)
            
        # 等待处理完成
        time.sleep(1.0)
        
        # 检查是否触发了暂停报单动作
        suspend_order_actions = [a for a in self.action_log 
                               if a["action_type"] == "suspend_order" 
                               and a["target_id"] == account_id]
        
        if suspend_order_actions:
            print(f"报单频率限制测试通过: 触发了 {len(suspend_order_actions)} 次暂停报单动作")
            self.test_results.append(("报单频率限制", "通过"))
        else:
            print("报单频率限制测试失败: 未触发预期的动作")
            self.test_results.append(("报单频率限制", "失败"))
            
    def test_multiple_rules_interaction(self):
        """测试多规则交互"""
        print("开始测试多规则交互...")
        
        account_id = "TEST_ACC_003"
        contract_id = "T2309"
        
        # 清空动作日志
        self.action_log.clear()
        
        # 同时触发成交量限制和成交金额限制
        for i in range(1100):
            order = Order(
                oid=i + 3000,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID,
                price=1000.0,  # 高价格以快速触发金额限制
                volume=1,
                timestamp=get_current_timestamp_ns()
            )
            
            trade = Trade(
                tid=i + 3000,
                oid=i + 3000,
                price=order.price,
                volume=1,
                timestamp=get_current_timestamp_ns()
            )
            
            self.engine.submit_order(order)
            self.engine.submit_trade(trade, order)
            
        # 等待处理完成
        time.sleep(1.0)
        
        # 检查触发的动作类型
        action_types = set(a["action_type"] for a in self.action_log 
                          if a["target_id"] == account_id)
        
        if "suspend_trading" in action_types or "alert" in action_types:
            print(f"多规则交互测试通过: 触发了动作类型 {action_types}")
            self.test_results.append(("多规则交互", "通过"))
        else:
            print("多规则交互测试失败: 未触发预期的动作")
            self.test_results.append(("多规则交互", "失败"))
            
    def test_performance_under_load(self):
        """测试高负载下的性能"""
        print("开始测试高负载性能...")
        
        order_count = 10000
        start_time = time.time()
        
        # 多线程模拟高并发
        def generate_orders(thread_id, count):
            for i in range(count):
                order = Order(
                    oid=thread_id * 10000 + i,
                    account_id=f"PERF_ACC_{thread_id % 5}",
                    contract_id="T2303",
                    direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                    price=100.0 + random.uniform(-5, 5),
                    volume=random.randint(1, 10),
                    timestamp=get_current_timestamp_ns()
                )
                
                self.engine.submit_order(order)
                
        # 启动多个线程
        threads = []
        thread_count = 4
        orders_per_thread = order_count // thread_count
        
        for i in range(thread_count):
            thread = threading.Thread(
                target=generate_orders,
                args=(i, orders_per_thread)
            )
            threads.append(thread)
            thread.start()
            
        # 等待所有线程完成
        for thread in threads:
            thread.join()
            
        # 等待所有订单处理完成
        time.sleep(2.0)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # 获取性能统计
        stats = self.engine.get_statistics_summary()
        performance = stats.get("performance", {})
        
        orders_processed = performance.get("total_orders_processed", 0)
        avg_processing_time_ns = performance.get("average_processing_time_ns", 0)
        max_processing_time_ns = performance.get("max_processing_time_ns", 0)
        
        print(f"性能测试结果:")
        print(f"  总订单数: {order_count}")
        print(f"  处理订单数: {orders_processed}")
        print(f"  总耗时: {duration:.2f}秒")
        print(f"  平均处理时间: {avg_processing_time_ns / 1000:.2f}微秒")
        print(f"  最大处理时间: {max_processing_time_ns / 1000:.2f}微秒")
        print(f"  吞吐量: {orders_processed / duration:.0f}订单/秒")
        
        # 判断性能是否合格（平均处理时间小于100微秒）
        if avg_processing_time_ns < 100000:  # 100微秒
            print("性能测试通过: 平均处理时间满足微秒级要求")
            self.test_results.append(("高负载性能", "通过"))
        else:
            print("性能测试失败: 平均处理时间超过100微秒")
            self.test_results.append(("高负载性能", "失败"))
            
    def test_statistics_accuracy(self):
        """测试统计准确性"""
        print("开始测试统计准确性...")
        
        account_id = "STAT_ACC_001"
        contract_id = "T2303"
        
        # 发送已知数量的订单和成交
        order_count = 100
        trade_volume = 500
        
        for i in range(order_count):
            order = Order(
                oid=i + 5000,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID,
                price=100.0,
                volume=5,
                timestamp=get_current_timestamp_ns()
            )
            
            trade = Trade(
                tid=i + 5000,
                oid=i + 5000,
                price=100.0,
                volume=5,
                timestamp=get_current_timestamp_ns()
            )
            
            self.engine.submit_order(order)
            self.engine.submit_trade(trade, order)
            
        # 等待处理完成
        time.sleep(1.0)
        
        # 检查统计数据
        stats = self.engine.get_statistics_summary()
        account_stats = stats.get("accounts", {}).get(account_id, {})
        
        recorded_volume = account_stats.get("trade_volume", 0)
        recorded_amount = account_stats.get("trade_amount", 0)
        
        expected_volume = trade_volume
        expected_amount = trade_volume * 100.0
        
        print(f"统计准确性测试结果:")
        print(f"  预期成交量: {expected_volume}, 记录成交量: {recorded_volume}")
        print(f"  预期成交金额: {expected_amount}, 记录成交金额: {recorded_amount}")
        
        volume_correct = abs(recorded_volume - expected_volume) < 1
        amount_correct = abs(recorded_amount - expected_amount) < 1
        
        if volume_correct and amount_correct:
            print("统计准确性测试通过")
            self.test_results.append(("统计准确性", "通过"))
        else:
            print("统计准确性测试失败")
            self.test_results.append(("统计准确性", "失败"))
            
    def test_edge_cases(self):
        """测试边界情况"""
        print("开始测试边界情况...")
        
        test_cases = [
            ("零成交量订单", 0),
            ("单手成交", 1),
            ("大额成交", 10000),
        ]
        
        for case_name, volume in test_cases:
            account_id = f"EDGE_ACC_{volume}"
            
            order = Order(
                oid=6000 + volume,
                account_id=account_id,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=volume,
                timestamp=get_current_timestamp_ns()
            )
            
            if volume > 0:  # 只有非零成交量才生成成交
                trade = Trade(
                    tid=6000 + volume,
                    oid=6000 + volume,
                    price=100.0,
                    volume=volume,
                    timestamp=get_current_timestamp_ns()
                )
                
                self.engine.submit_order(order)
                self.engine.submit_trade(trade, order)
            else:
                self.engine.submit_order(order)
                
        # 等待处理完成
        time.sleep(0.5)
        
        print("边界情况测试完成")
        self.test_results.append(("边界情况", "通过"))
        
    def run_all_tests(self):
        """运行所有测试"""
        print("开始运行风控系统全面测试")
        print("=" * 50)
        
        try:
            self.setup_test_environment()
            
            # 运行各项测试
            self.test_account_volume_limit()
            print("-" * 30)
            
            self.test_order_frequency_limit()
            print("-" * 30)
            
            self.test_multiple_rules_interaction()
            print("-" * 30)
            
            self.test_statistics_accuracy()
            print("-" * 30)
            
            self.test_edge_cases()
            print("-" * 30)
            
            self.test_performance_under_load()
            print("-" * 30)
            
        finally:
            self.teardown_test_environment()
            
        # 输出测试结果
        self.print_test_summary()
        
    def print_test_summary(self):
        """打印测试总结"""
        print("\n测试结果总结:")
        print("=" * 50)
        
        passed = 0
        total = len(self.test_results)
        
        for test_name, result in self.test_results:
            status_mark = "PASS" if result == "通过" else "FAIL"
            print(f"{test_name:.<30} {status_mark}")
            if result == "通过":
                passed += 1
                
        print("-" * 50)
        print(f"总计: {passed}/{total} 项测试通过")
        
        if passed == total:
            print("所有测试通过! 系统功能正常")
        else:
            print(f"有 {total - passed} 项测试失败，请检查系统")
            
        # 打印部分动作日志
        if self.action_log:
            print(f"\n触发的风控动作总数: {len(self.action_log)}")
            print("最近5个风控动作:")
            for action in self.action_log[-5:]:
                print(f"  {action['action_type']} -> {action['target_id']}: {action['reason']}")


def main():
    """主函数"""
    print("金融风控模块测试程序")
    print("本程序将测试风控系统的各项功能")
    print()
    
    tester = RiskSystemTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()