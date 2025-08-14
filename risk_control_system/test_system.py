"""
风控系统测试
包含各种场景的测试用例
"""
import time
import random
from typing import List

from risk_control_system.models import Order, Trade, Direction
from risk_control_system.config import RiskControlConfig, RiskRule, RuleCondition, RuleAction, ActionType, MetricType, DimensionType
from risk_control_system.engine import RiskControlEngine


class TestScenarios:
    """测试场景集合"""
    
    @staticmethod
    def generate_timestamp(offset_seconds=0):
        """生成时间戳（纳秒）"""
        return int((time.time() + offset_seconds) * 1_000_000_000)
    
    @staticmethod
    def test_volume_limit():
        """测试1：单账户成交量限制"""
        print("\n=== 测试1：单账户成交量限制 ===")
        
        engine = RiskControlEngine()
        account_id = "ACC_001"
        contract_id = "T2303"
        
        # 生成订单和成交
        trades_processed = 0
        actions_triggered = []
        
        for i in range(120):  # 生成120笔成交，每笔10手
            # 创建订单
            order = Order(
                oid=i + 1,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                price=100.0 + random.uniform(-0.5, 0.5),
                volume=10,
                timestamp=TestScenarios.generate_timestamp(i * 0.1)
            )
            
            # 处理订单
            order_actions = engine.process_order(order)
            if order_actions:
                actions_triggered.extend(order_actions)
            
            # 创建成交
            trade = Trade(
                tid=i + 1000,
                oid=order.oid,
                price=order.price,
                volume=order.volume,
                timestamp=order.timestamp + 1000000  # 1毫秒后成交
            )
            
            # 处理成交
            trade_actions = engine.process_trade(trade)
            if trade_actions:
                actions_triggered.extend(trade_actions)
                print(f"在第{i+1}笔成交后触发风控: {trade_actions[0].reason}")
                break
            
            trades_processed += 1
        
        # 统计结果
        total_volume = engine.statistics.get_statistic(
            DimensionType.ACCOUNT, account_id, MetricType.TRADE_VOLUME
        )
        
        print(f"处理成交数: {trades_processed}")
        print(f"账户总成交量: {total_volume}手")
        print(f"触发风控动作数: {len(actions_triggered)}")
        
        if actions_triggered:
            print(f"风控动作类型: {actions_triggered[0].action_type}")
            print(f"账户状态: {engine.get_account_status(account_id)}")
    
    @staticmethod
    def test_order_frequency():
        """测试2：报单频率控制"""
        print("\n=== 测试2：报单频率控制 ===")
        
        engine = RiskControlEngine()
        account_id = "ACC_002"
        contract_id = "TF2303"
        
        # 在1秒内发送60个订单
        orders_sent = 0
        actions_triggered = []
        base_timestamp = TestScenarios.generate_timestamp()
        
        for i in range(60):
            order = Order(
                oid=i + 2000,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID,
                price=95.0,
                volume=1,
                timestamp=base_timestamp + i * 10_000_000  # 每10毫秒一个订单
            )
            
            actions = engine.process_order(order)
            if actions:
                actions_triggered.extend(actions)
                print(f"在第{i+1}个订单时触发风控: {actions[0].reason}")
                break
            
            orders_sent += 1
        
        # 获取统计
        order_freq = engine.statistics.get_statistic(
            DimensionType.ACCOUNT, account_id, MetricType.ORDER_FREQUENCY,
            base_timestamp + 1_000_000_000
        )
        
        print(f"发送订单数: {orders_sent}")
        print(f"当前订单频率: {order_freq}个/秒")
        print(f"触发风控动作数: {len(actions_triggered)}")
        
        if actions_triggered:
            print(f"风控动作类型: {actions_triggered[0].action_type}")
            print(f"账户状态: {engine.get_account_status(account_id)}")
        
        # 测试自动恢复
        print("\n等待自动恢复...")
        time.sleep(2)  # 实际系统中会根据配置的duration自动恢复
        
    @staticmethod
    def test_multi_dimension():
        """测试3：多维度统计"""
        print("\n=== 测试3：多维度统计 ===")
        
        engine = RiskControlEngine()
        
        # 创建多个账户在不同合约上的交易
        test_data = [
            ("ACC_001", "T2303", 50),   # 10年期国债
            ("ACC_001", "T2306", 30),   # 10年期国债
            ("ACC_002", "T2303", 40),   # 10年期国债
            ("ACC_002", "TF2303", 60),  # 5年期国债
        ]
        
        for account_id, contract_id, volume in test_data:
            order = Order(
                oid=random.randint(10000, 99999),
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID,
                price=100.0,
                volume=volume,
                timestamp=TestScenarios.generate_timestamp()
            )
            
            trade = Trade(
                tid=random.randint(100000, 999999),
                oid=order.oid,
                price=order.price,
                volume=order.volume,
                timestamp=order.timestamp + 1000000
            )
            
            engine.process_order(order)
            engine.process_trade(trade)
        
        # 输出统计结果
        print("\n账户维度统计:")
        for account in ["ACC_001", "ACC_002"]:
            volume = engine.statistics.get_statistic(
                DimensionType.ACCOUNT, account, MetricType.TRADE_VOLUME
            )
            print(f"  {account}: {volume}手")
        
        print("\n合约维度统计:")
        for contract in ["T2303", "T2306", "TF2303"]:
            volume = engine.statistics.get_statistic(
                DimensionType.CONTRACT, contract, MetricType.TRADE_VOLUME
            )
            print(f"  {contract}: {volume}手")
        
        print("\n产品维度统计:")
        for product in ["T", "TF"]:
            volume = engine.statistics.get_statistic(
                DimensionType.PRODUCT, product, MetricType.TRADE_VOLUME
            )
            print(f"  {product}: {volume}手")
    
    @staticmethod
    def test_custom_rule():
        """测试4：自定义规则"""
        print("\n=== 测试4：自定义规则 ===")
        
        # 创建自定义配置
        config = RiskControlConfig()
        
        # 添加成交金额限制规则
        amount_rule = RiskRule(
            rule_id="AMOUNT_LIMIT_001",
            name="单账户日成交金额限制",
            description="账户日成交金额超过100万时警告",
            conditions=[
                RuleCondition(
                    metric_type=MetricType.TRADE_AMOUNT,
                    threshold=1000000,
                    comparison="gt",
                    dimension=DimensionType.ACCOUNT
                )
            ],
            actions=[
                RuleAction(
                    action_type=ActionType.WARNING,
                    params={"reason": "日成交金额超限", "notification": "email"},
                    priority=5
                )
            ]
        )
        
        config.add_rule(amount_rule)
        engine = RiskControlEngine(config)
        
        # 生成大额交易
        account_id = "ACC_003"
        for i in range(5):
            order = Order(
                oid=i + 5000,
                account_id=account_id,
                contract_id="TS2303",
                direction=Direction.BID,
                price=10000.0,  # 高价格
                volume=30,      # 大数量
                timestamp=TestScenarios.generate_timestamp(i)
            )
            
            trade = Trade(
                tid=i + 6000,
                oid=order.oid,
                price=order.price,
                volume=order.volume,
                timestamp=order.timestamp + 1000000
            )
            
            engine.process_order(order)
            actions = engine.process_trade(trade)
            
            if actions:
                print(f"第{i+1}笔交易触发: {actions[0].reason}")
        
        # 输出统计
        amount = engine.statistics.get_statistic(
            DimensionType.ACCOUNT, account_id, MetricType.TRADE_AMOUNT
        )
        print(f"账户总成交金额: {amount:,.2f}")
    
    @staticmethod
    def test_performance():
        """测试5：性能测试"""
        print("\n=== 测试5：性能测试 ===")
        
        engine = RiskControlEngine()
        
        # 准备测试数据
        num_orders = 10000
        orders = []
        trades = []
        
        for i in range(num_orders):
            order = Order(
                oid=i,
                account_id=f"ACC_{i % 100:03d}",  # 100个账户
                contract_id=f"T230{i % 4 + 3}",   # 4个合约
                direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                price=100.0 + random.uniform(-1, 1),
                volume=random.randint(1, 10),
                timestamp=TestScenarios.generate_timestamp(i * 0.001)
            )
            orders.append(order)
            
            if random.random() < 0.8:  # 80%成交率
                trade = Trade(
                    tid=i + 100000,
                    oid=order.oid,
                    price=order.price,
                    volume=order.volume,
                    timestamp=order.timestamp + random.randint(1000, 10000)
                )
                trades.append(trade)
        
        # 测试订单处理性能
        start_time = time.time()
        for order in orders:
            engine.process_order(order)
        order_time = time.time() - start_time
        
        # 测试成交处理性能
        start_time = time.time()
        for trade in trades:
            engine.process_trade(trade)
        trade_time = time.time() - start_time
        
        # 输出性能指标
        print(f"订单处理数量: {len(orders)}")
        print(f"订单处理时间: {order_time:.3f}秒")
        print(f"订单处理速度: {len(orders)/order_time:.0f}笔/秒")
        print(f"\n成交处理数量: {len(trades)}")
        print(f"成交处理时间: {trade_time:.3f}秒")
        print(f"成交处理速度: {len(trades)/trade_time:.0f}笔/秒")
        
        # 统计触发的风控
        triggered_accounts = 0
        for i in range(100):
            account_id = f"ACC_{i:03d}"
            if engine.is_account_suspended(account_id) or engine.is_order_suspended(account_id):
                triggered_accounts += 1
        
        print(f"\n触发风控的账户数: {triggered_accounts}")


def main():
    """运行所有测试"""
    print("金融风控系统测试")
    print("=" * 50)
    
    # 运行各项测试
    TestScenarios.test_volume_limit()
    TestScenarios.test_order_frequency()
    TestScenarios.test_multi_dimension()
    TestScenarios.test_custom_rule()
    TestScenarios.test_performance()
    
    print("\n" + "=" * 50)
    print("测试完成")


if __name__ == "__main__":
    main()