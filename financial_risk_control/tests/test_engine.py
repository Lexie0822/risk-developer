"""
风控引擎测试用例
"""
import unittest
import time
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models import Order, Trade, Direction, ActionType
from src.config import create_default_config, VolumeControlConfig, FrequencyControlConfig, MetricType, AggregationLevel
from src.engine import RiskControlEngine


class TestRiskControlEngine(unittest.TestCase):
    """风控引擎测试"""
    
    def setUp(self):
        """测试前准备"""
        # 创建默认配置
        self.config = create_default_config()
        # 创建引擎
        self.engine = RiskControlEngine(self.config)
        # 基准时间戳（纳秒）
        self.base_timestamp = int(datetime.now().timestamp() * 1_000_000_000)
    
    def _create_order(self, oid: int, account_id: str, contract_id: str, 
                     volume: int = 10, price: float = 100.0, 
                     direction: Direction = Direction.BID,
                     timestamp_offset_ms: int = 0) -> Order:
        """创建测试订单"""
        return Order(
            oid=oid,
            account_id=account_id,
            contract_id=contract_id,
            direction=direction,
            price=price,
            volume=volume,
            timestamp=self.base_timestamp + timestamp_offset_ms * 1_000_000
        )
    
    def _create_trade(self, tid: int, oid: int, volume: int = 10, 
                     price: float = 100.0, timestamp_offset_ms: int = 0) -> Trade:
        """创建测试成交"""
        return Trade(
            tid=tid,
            oid=oid,
            price=price,
            volume=volume,
            timestamp=self.base_timestamp + timestamp_offset_ms * 1_000_000
        )
    
    def test_volume_control_daily_limit(self):
        """测试日成交量限制"""
        print("\n=== 测试日成交量限制 ===")
        
        account_id = "ACC_001"
        contract_id = "T2303"
        
        # 前990手正常成交
        for i in range(99):
            order = self._create_order(i, account_id, contract_id, volume=10)
            trade = self._create_trade(1000+i, i, volume=10)
            
            order_actions = self.engine.process_order(order)
            trade_actions = self.engine.process_trade(trade)
            
            self.assertEqual(len(order_actions), 0)
            self.assertEqual(len(trade_actions), 0)
        
        # 第1000手触发限制
        order = self._create_order(99, account_id, contract_id, volume=10)
        trade = self._create_trade(1099, 99, volume=10)
        
        order_actions = self.engine.process_order(order)
        trade_actions = self.engine.process_trade(trade)
        
        self.assertEqual(len(order_actions), 0)
        self.assertEqual(len(trade_actions), 1)
        
        action = trade_actions[0]
        self.assertEqual(action.action_type, ActionType.SUSPEND_ACCOUNT)
        self.assertEqual(action.target_id, account_id)
        
        print(f"成交量限制触发: {action.reason}")
        
        # 验证统计
        stats = self.engine.get_statistics(account_id)
        daily_volume = stats['trade_volume']['account']['daily']['value']
        self.assertEqual(daily_volume, 1000)
        print(f"当前日成交量: {daily_volume}")
    
    def test_order_frequency_control(self):
        """测试报单频率控制"""
        print("\n=== 测试报单频率控制 ===")
        
        account_id = "ACC_002"
        contract_id = "T2303"
        
        # 1秒内发送50个订单（不触发）
        for i in range(50):
            order = self._create_order(200+i, account_id, contract_id, timestamp_offset_ms=i*10)
            actions = self.engine.process_order(order)
            self.assertEqual(len(actions), 0)
        
        # 第51个订单触发频率限制
        order = self._create_order(250, account_id, contract_id, timestamp_offset_ms=500)
        actions = self.engine.process_order(order)
        
        # 应该有两个动作：暂停报单和拦截订单
        self.assertGreaterEqual(len(actions), 2)
        
        suspend_action = next((a for a in actions if a.action_type == ActionType.SUSPEND_ORDER), None)
        block_action = next((a for a in actions if a.action_type == ActionType.BLOCK_ORDER), None)
        
        self.assertIsNotNone(suspend_action)
        self.assertIsNotNone(block_action)
        
        print(f"频率控制触发: {suspend_action.reason}")
        
        # 后续订单应该被拦截
        order = self._create_order(251, account_id, contract_id, timestamp_offset_ms=600)
        actions = self.engine.process_order(order)
        self.assertTrue(any(a.action_type == ActionType.BLOCK_ORDER for a in actions))
        
        # 等待窗口过期后应该自动恢复
        time.sleep(1.1)  # 等待超过1秒
        order = self._create_order(252, account_id, contract_id, timestamp_offset_ms=2000)
        actions = self.engine.process_order(order)
        self.assertEqual(len(actions), 0)
        print("频率降低后自动恢复")
    
    def test_product_aggregation(self):
        """测试产品维度聚合"""
        print("\n=== 测试产品维度聚合 ===")
        
        # 添加产品维度的成交量规则
        product_volume_rule = VolumeControlConfig(
            rule_name="product_volume_limit",
            description="产品维度成交量限制",
            metric_type=MetricType.TRADE_VOLUME,
            threshold=2000,  # 2000手
            aggregation_level=AggregationLevel.PRODUCT,
            actions=["warning"],
            priority=5
        )
        self.engine.config.add_rule(product_volume_rule)
        self.engine.reload_config(self.engine.config)
        
        # 在同一产品的不同合约上交易
        contracts = ["T2303", "T2306", "T2309"]
        account_id = "ACC_003"
        
        total_volume = 0
        for i, contract in enumerate(contracts):
            for j in range(70):  # 每个合约700手
                oid = 300 + i*100 + j
                order = self._create_order(oid, account_id, contract, volume=10)
                trade = self._create_trade(3000+oid, oid, volume=10)
                
                order_actions = self.engine.process_order(order)
                trade_actions = self.engine.process_trade(trade)
                
                total_volume += 10
                
                if total_volume > 2000:
                    # 超过产品维度限制
                    self.assertTrue(any(a.action_type == ActionType.WARNING for a in trade_actions))
                    if trade_actions:
                        print(f"产品维度限制触发 - 合约: {contract}, 总量: {total_volume}")
                        break
            
            if total_volume > 2000:
                break
    
    def test_multiple_rules_interaction(self):
        """测试多规则交互"""
        print("\n=== 测试多规则交互 ===")
        
        account_id = "ACC_004"
        contract_id = "T2303"
        
        # 快速发送大量订单，同时触发频率和成交量限制
        for i in range(60):
            order = self._create_order(400+i, account_id, contract_id, 
                                     volume=20, timestamp_offset_ms=i*15)
            trade = self._create_trade(4000+i, 400+i, volume=20, 
                                     timestamp_offset_ms=i*15+5)
            
            order_actions = self.engine.process_order(order)
            trade_actions = self.engine.process_trade(trade)
            
            if order_actions:
                print(f"订单 {400+i} 触发动作: {[a.action_type.value for a in order_actions]}")
            if trade_actions:
                print(f"成交 {4000+i} 触发动作: {[a.action_type.value for a in trade_actions]}")
    
    def test_performance(self):
        """测试性能"""
        print("\n=== 测试性能 ===")
        
        # 测试大批量订单处理
        start_time = time.time()
        order_count = 10000
        
        for i in range(order_count):
            order = self._create_order(
                10000+i, 
                f"ACC_{i%100:03d}",  # 100个不同账户
                f"T230{i%4+3}",      # 4个不同合约
                volume=1 + i%10
            )
            self.engine.process_order(order)
            
            # 10%的订单生成成交
            if i % 10 == 0:
                trade = self._create_trade(100000+i, 10000+i, volume=order.volume)
                self.engine.process_trade(trade)
        
        elapsed = time.time() - start_time
        ops_per_sec = order_count / elapsed
        
        print(f"处理 {order_count} 个订单耗时: {elapsed:.3f} 秒")
        print(f"处理速度: {ops_per_sec:.0f} 订单/秒")
        print(f"平均延迟: {elapsed/order_count*1000:.3f} 毫秒/订单")
        
        # 性能应该满足要求
        self.assertGreater(ops_per_sec, 1000)  # 至少1000订单/秒
    
    def test_daily_reset(self):
        """测试日终重置"""
        print("\n=== 测试日终重置 ===")
        
        account_id = "ACC_005"
        contract_id = "T2303"
        
        # 生成一些成交
        for i in range(10):
            order = self._create_order(500+i, account_id, contract_id, volume=50)
            trade = self._create_trade(5000+i, 500+i, volume=50)
            self.engine.process_order(order)
            self.engine.process_trade(trade)
        
        # 验证统计
        stats_before = self.engine.get_statistics(account_id)
        volume_before = stats_before['trade_volume']['account']['daily']['value']
        self.assertEqual(volume_before, 500)
        
        # 执行日终重置
        self.engine.reset_daily_stats()
        
        # 验证统计已清零
        stats_after = self.engine.get_statistics(account_id)
        volume_after = stats_after.get('trade_volume', {}).get('account', {}).get('daily', {}).get('value', 0)
        self.assertEqual(volume_after, 0)
        
        print(f"日终重置前成交量: {volume_before}")
        print(f"日终重置后成交量: {volume_after}")
    
    def test_suspended_targets(self):
        """测试暂停目标查询"""
        print("\n=== 测试暂停目标查询 ===")
        
        # 触发一些账户暂停
        for i in range(3):
            account_id = f"ACC_10{i}"
            # 快速发送大量订单触发频率控制
            for j in range(60):
                order = self._create_order(600+i*100+j, account_id, "T2303", 
                                         timestamp_offset_ms=j*10)
                self.engine.process_order(order)
        
        # 查询暂停目标
        suspended = self.engine.get_suspended_targets()
        print(f"暂停目标: {suspended}")
        
        self.assertIn("order_frequency_control", suspended)
        self.assertGreaterEqual(len(suspended["order_frequency_control"]), 3)


def run_test_suite():
    """运行完整测试套件"""
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRiskControlEngine)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回测试结果
    return result.wasSuccessful()


if __name__ == "__main__":
    # 运行测试
    success = run_test_suite()
    
    if success:
        print("\n✅ 所有测试通过!")
    else:
        print("\n❌ 测试失败!")
        sys.exit(1)