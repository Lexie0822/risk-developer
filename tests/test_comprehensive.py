"""
完整测试套件：覆盖所有风控规则和扩展点。

测试内容：
1. 单账户成交量限制规则（支持多维度）
2. 报单频率控制规则（支持动态阈值调整）
3. 撤单量监控规则（扩展点）
4. 多维统计引擎（合约、产品、交易所、账户组维度）
5. 动态规则配置和热更新
6. 高并发性能测试
"""

import unittest
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List

from risk_engine import RiskEngine, EngineConfig, Order, Trade, CancelOrder, Direction, Action, MetricType
from risk_engine.rules import (
    AccountTradeMetricLimitRule, 
    OrderRateLimitRule, 
    CancelRateLimitRule,
    Rule, 
    RuleContext, 
    RuleResult
)
from risk_engine.config import (
    RiskEngineConfig, 
    VolumeLimitRuleConfig, 
    OrderRateLimitRuleConfig,
    CancelRuleLimitConfig,
    StatsDimension
)
from risk_engine.dimensions import ExtensibleDimensionResolver


class ActionCollector:
    """动作收集器，用于测试验证。"""
    
    def __init__(self):
        self.actions = []
        self.lock = threading.Lock()
    
    def __call__(self, action, rule_id, obj):
        with self.lock:
            self.actions.append((action, rule_id, obj))
    
    def get_actions(self):
        with self.lock:
            return list(self.actions)
    
    def clear(self):
        with self.lock:
            self.actions.clear()
    
    def has_action(self, action_type):
        with self.lock:
            return any(a[0] == action_type for a in self.actions)


class TestComprehensiveRiskEngine(unittest.TestCase):
    """综合风控引擎测试。"""
    
    def setUp(self):
        """测试初始化。"""
        self.action_collector = ActionCollector()
        self.base_timestamp = int(time.time() * 1_000_000_000)
    
    def create_engine_with_all_rules(self):
        """创建包含所有规则的引擎。"""
        config = EngineConfig(
            contract_to_product={
                "T2303": "T10Y", "T2306": "T10Y",  # 10年期国债期货
                "IF2303": "IF", "IF2306": "IF",     # 沪深300指数期货
                "CU2303": "CU", "CU2306": "CU",    # 铜期货
            },
            contract_to_exchange={
                "T2303": "CFFEX", "T2306": "CFFEX",
                "IF2303": "CFFEX", "IF2306": "CFFEX", 
                "CU2303": "SHFE", "CU2306": "SHFE",
            },
            deduplicate_actions=True,
        )
        
        engine = RiskEngine(config, action_sink=self.action_collector)
        
        # 添加成交量限制规则（产品维度）
        volume_rule = AccountTradeMetricLimitRule(
            rule_id="VOLUME-LIMIT-PRODUCT",
            metric=MetricType.TRADE_VOLUME,
            threshold=1000,  # 1000手
            actions=(Action.SUSPEND_ACCOUNT_TRADING,),
            by_account=True,
            by_product=True,
            by_contract=False,
        )
        
        # 添加成交量限制规则（合约维度）
        volume_rule_contract = AccountTradeMetricLimitRule(
            rule_id="VOLUME-LIMIT-CONTRACT",
            metric=MetricType.TRADE_VOLUME,
            threshold=500,  # 500手
            actions=(Action.SUSPEND_CONTRACT,),
            by_account=True,
            by_contract=True,
            by_product=False,
        )
        
        # 添加成交金额限制规则
        notional_rule = AccountTradeMetricLimitRule(
            rule_id="NOTIONAL-LIMIT",
            metric=MetricType.TRADE_NOTIONAL,
            threshold=1000000,  # 100万
            actions=(Action.ALERT,),
            by_account=True,
            by_product=True,
        )
        
        # 添加报单频率限制规则
        order_rate_rule = OrderRateLimitRule(
            rule_id="ORDER-RATE-LIMIT",
            threshold=50,  # 50次/秒
            window_seconds=1,
            suspend_actions=(Action.SUSPEND_ORDERING,),
            resume_actions=(Action.RESUME_ORDERING,),
            dimension="account",
        )
        
        # 添加撤单频率限制规则（扩展点）
        cancel_rate_rule = CancelRateLimitRule(
            rule_id="CANCEL-RATE-LIMIT",
            threshold=20,  # 20次/秒
            window_seconds=1,
            actions=(Action.SUSPEND_ORDERING,),
            dimension="account",
        )
        
        # 添加撤单量监控规则
        cancel_volume_rule = AccountTradeMetricLimitRule(
            rule_id="CANCEL-VOLUME-LIMIT",
            metric=MetricType.CANCEL_COUNT,
            threshold=100,  # 100次/天
            actions=(Action.ALERT,),
            by_account=True,
        )
        
        engine.add_rule(volume_rule)
        engine.add_rule(volume_rule_contract)
        engine.add_rule(notional_rule)
        engine.add_rule(order_rate_rule)
        engine.add_rule(cancel_rate_rule)
        engine.add_rule(cancel_volume_rule)
        
        return engine
    
    def test_single_account_volume_limit_product_dimension(self):
        """测试单账户成交量限制（产品维度）。"""
        engine = self.create_engine_with_all_rules()
        self.action_collector.clear()
        
        # 同一产品（T10Y）不同合约的成交应累计
        trades = [
            Trade(1, 1, 100.0, 400, self.base_timestamp, "ACC_001", "T2303"),
            Trade(2, 2, 100.0, 300, self.base_timestamp + 1000, "ACC_001", "T2306"),
            Trade(3, 3, 100.0, 200, self.base_timestamp + 2000, "ACC_001", "T2303"),
            Trade(4, 4, 100.0, 150, self.base_timestamp + 3000, "ACC_001", "T2306"),
        ]
        
        for trade in trades:
            engine.on_trade(trade)
        
        # 总成交量：400+300+200+150 = 1050 > 1000，应触发暂停
        self.assertTrue(self.action_collector.has_action(Action.SUSPEND_ACCOUNT_TRADING))
        
        # 不同产品应独立计算
        engine.on_trade(Trade(5, 5, 100.0, 600, self.base_timestamp + 4000, "ACC_001", "IF2303"))
        # IF产品成交量600 < 1000，不应触发
        actions = self.action_collector.get_actions()
        trading_suspensions = [a for a in actions if a[0] == Action.SUSPEND_ACCOUNT_TRADING]
        self.assertEqual(len(trading_suspensions), 1)  # 只有T10Y产品触发
    
    def test_single_account_volume_limit_contract_dimension(self):
        """测试单账户成交量限制（合约维度）。"""
        engine = self.create_engine_with_all_rules()
        self.action_collector.clear()
        
        # 单合约成交量测试
        trades = [
            Trade(1, 1, 100.0, 300, self.base_timestamp, "ACC_002", "T2303"),
            Trade(2, 2, 100.0, 250, self.base_timestamp + 1000, "ACC_002", "T2303"),
        ]
        
        for trade in trades:
            engine.on_trade(trade)
        
        # T2303合约成交量：300+250 = 550 > 500，应触发合约暂停
        self.assertTrue(self.action_collector.has_action(Action.SUSPEND_CONTRACT))
        
        # 同一产品不同合约应独立计算
        engine.on_trade(Trade(3, 3, 100.0, 400, self.base_timestamp + 2000, "ACC_002", "T2306"))
        # T2306合约成交量400 < 500，不应触发
        actions = self.action_collector.get_actions()
        contract_suspensions = [a for a in actions if a[0] == Action.SUSPEND_CONTRACT]
        self.assertEqual(len(contract_suspensions), 1)  # 只有T2303合约触发
    
    def test_order_rate_limit_with_recovery(self):
        """测试报单频率控制（包含暂停和恢复）。"""
        engine = self.create_engine_with_all_rules()
        self.action_collector.clear()
        
        # 在1秒内提交51笔订单，超过阈值50
        orders = []
        for i in range(51):
            order = Order(
                oid=i+1,
                account_id="ACC_003", 
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0 + i * 0.01,
                volume=1,
                timestamp=self.base_timestamp + i * 1000000  # 1ms间隔
            )
            orders.append(order)
            engine.on_order(order)
        
        # 应触发暂停报单
        self.assertTrue(self.action_collector.has_action(Action.SUSPEND_ORDERING))
        
        # 清除之前的动作记录
        self.action_collector.clear()
        
        # 1秒后提交1笔订单，应触发恢复
        recovery_order = Order(
            oid=100,
            account_id="ACC_003",
            contract_id="T2303", 
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=self.base_timestamp + 1_000_000_000 + 1000000  # 1秒后
        )
        engine.on_order(recovery_order)
        
        # 应触发恢复报单
        self.assertTrue(self.action_collector.has_action(Action.RESUME_ORDERING))
    
    def test_cancel_order_monitoring(self):
        """测试撤单量监控（扩展点）。"""
        engine = self.create_engine_with_all_rules()
        self.action_collector.clear()
        
        # 先提交一些订单
        for i in range(10):
            order = Order(
                oid=i+1,
                account_id="ACC_004",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=10,
                timestamp=self.base_timestamp + i * 1000000
            )
            engine.on_order(order)
        
        # 提交大量撤单，超过阈值100
        for i in range(101):
            cancel = CancelOrder(
                cancel_id=i+1,
                oid=i % 10 + 1,  # 循环撤销前面的订单
                timestamp=self.base_timestamp + 10000000 + i * 1000000,
                account_id="ACC_004",
                contract_id="T2303",
                cancel_volume=10
            )
            engine.on_cancel(cancel)
        
        # 应触发告警
        self.assertTrue(self.action_collector.has_action(Action.ALERT))
    
    def test_cancel_rate_limit(self):
        """测试撤单频率控制（扩展点）。"""
        engine = self.create_engine_with_all_rules()
        self.action_collector.clear()
        
        # 先提交订单
        for i in range(25):
            order = Order(
                oid=i+1,
                account_id="ACC_005",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=self.base_timestamp + i * 1000000
            )
            engine.on_order(order)
        
        # 在1秒内提交21笔撤单，超过阈值20
        for i in range(21):
            cancel = CancelOrder(
                cancel_id=i+1,
                oid=i+1,
                timestamp=self.base_timestamp + 30000000 + i * 1000000,  # 1ms间隔
                account_id="ACC_005",
                contract_id="T2303"
            )
            engine.on_cancel(cancel)
        
        # 应触发暂停报单
        self.assertTrue(self.action_collector.has_action(Action.SUSPEND_ORDERING))
    
    def test_multi_dimension_stats_exchange(self):
        """测试多维统计引擎（交易所维度）。"""
        # 创建支持交易所维度的引擎
        config = EngineConfig(
            contract_to_product={"T2303": "T10Y", "IF2303": "IF"},
            contract_to_exchange={"T2303": "CFFEX", "IF2303": "CFFEX"},
        )
        
        engine = RiskEngine(config, action_sink=self.action_collector)
        
        # 添加交易所维度的成交量限制
        exchange_rule = AccountTradeMetricLimitRule(
            rule_id="EXCHANGE-VOLUME-LIMIT",
            metric=MetricType.TRADE_VOLUME,
            threshold=1500,
            actions=(Action.SUSPEND_EXCHANGE,),
            by_account=True,
            by_exchange=True,
            by_product=False,
            by_contract=False,
        )
        
        engine.add_rule(exchange_rule)
        self.action_collector.clear()
        
        # 同一交易所不同产品的成交应累计
        trades = [
            Trade(1, 1, 100.0, 800, self.base_timestamp, "ACC_006", "T2303"),
            Trade(2, 2, 100.0, 800, self.base_timestamp + 1000, "ACC_006", "IF2303"),
        ]
        
        for trade in trades:
            engine.on_trade(trade)
        
        # CFFEX交易所总成交量：800+800 = 1600 > 1500，应触发暂停
        self.assertTrue(self.action_collector.has_action(Action.SUSPEND_EXCHANGE))
    
    def test_dynamic_threshold_adjustment(self):
        """测试动态阈值调整。"""
        engine = self.create_engine_with_all_rules()
        
        # 获取报单频率规则并动态调整阈值
        for rule in engine._rules:
            if isinstance(rule, OrderRateLimitRule) and rule.rule_id == "ORDER-RATE-LIMIT":
                # 动态调整阈值从50降到10
                rule.threshold = 10
                rule.window_seconds = 1
                break
        
        self.action_collector.clear()
        
        # 提交11笔订单，应触发暂停（新阈值10）
        for i in range(11):
            order = Order(
                oid=i+1,
                account_id="ACC_007",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=self.base_timestamp + i * 1000000
            )
            engine.on_order(order)
        
        # 应触发暂停（阈值已调整为10）
        self.assertTrue(self.action_collector.has_action(Action.SUSPEND_ORDERING))
    
    def test_multiple_actions_per_rule(self):
        """测试一个规则关联多个Action（扩展点）。"""
        config = EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            deduplicate_actions=True,
        )
        
        engine = RiskEngine(config, action_sink=self.action_collector)
        
        # 创建具有多个动作的规则
        multi_action_rule = AccountTradeMetricLimitRule(
            rule_id="MULTI-ACTION-RULE",
            metric=MetricType.TRADE_VOLUME,
            threshold=100,
            actions=(Action.ALERT, Action.SUSPEND_ACCOUNT_TRADING, Action.INCREASE_MARGIN),
            by_account=True,
        )
        
        engine.add_rule(multi_action_rule)
        self.action_collector.clear()
        
        # 触发规则
        trade = Trade(1, 1, 100.0, 150, self.base_timestamp, "ACC_008", "T2303")
        engine.on_trade(trade)
        
        # 应触发所有配置的动作
        actions = self.action_collector.get_actions()
        action_types = [a[0] for a in actions]
        
        self.assertIn(Action.ALERT, action_types)
        self.assertIn(Action.SUSPEND_ACCOUNT_TRADING, action_types)
        self.assertIn(Action.INCREASE_MARGIN, action_types)
    
    def test_custom_rule_development(self):
        """测试自定义规则开发。"""
        
        class CustomPositionLimitRule(Rule):
            """自定义持仓限制规则。"""
            
            def __init__(self, rule_id: str, position_limit: int):
                self.rule_id = rule_id
                self.position_limit = position_limit
                self.positions = {}  # 简单的持仓跟踪
            
            def on_trade(self, ctx, trade):
                # 更新持仓
                key = (trade.account_id, trade.contract_id)
                current_pos = self.positions.get(key, 0)
                new_pos = current_pos + trade.volume
                self.positions[key] = new_pos
                
                if abs(new_pos) > self.position_limit:
                    return RuleResult(
                        actions=[Action.REDUCE_POSITION],
                        reasons=[f"持仓 {new_pos} 超过限制 {self.position_limit}"]
                    )
                return None
        
        engine = self.create_engine_with_all_rules()
        custom_rule = CustomPositionLimitRule("POSITION-LIMIT", 1000)
        engine.add_rule(custom_rule)
        
        self.action_collector.clear()
        
        # 触发持仓限制
        trade = Trade(1, 1, 100.0, 1500, self.base_timestamp, "ACC_009", "T2303")
        engine.on_trade(trade)
        
        # 应触发减仓动作
        self.assertTrue(self.action_collector.has_action(Action.REDUCE_POSITION))
    
    def test_high_concurrency_performance(self):
        """测试高并发性能。"""
        engine = self.create_engine_with_all_rules()
        
        def process_orders(thread_id, num_orders):
            """处理订单的工作函数。"""
            for i in range(num_orders):
                order = Order(
                    oid=thread_id * 10000 + i,
                    account_id=f"ACC_{thread_id:03d}",
                    contract_id="T2303",
                    direction=Direction.BID,
                    price=100.0 + i * 0.01,
                    volume=1,
                    timestamp=self.base_timestamp + thread_id * 1000000 + i * 1000
                )
                engine.on_order(order)
        
        # 10个线程，每个处理1000笔订单
        num_threads = 10
        orders_per_thread = 1000
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [
                executor.submit(process_orders, i, orders_per_thread) 
                for i in range(num_threads)
            ]
            
            # 等待所有任务完成
            for future in futures:
                future.result()
        
        end_time = time.time()
        total_time = end_time - start_time
        total_orders = num_threads * orders_per_thread
        throughput = total_orders / total_time
        
        print(f"并发测试结果：")
        print(f"  总订单数: {total_orders:,}")
        print(f"  总时间: {total_time:.3f}秒")
        print(f"  吞吐量: {throughput:,.0f} 订单/秒")
        
        # 验证性能目标（至少10万订单/秒）
        self.assertGreater(throughput, 100000, "吞吐量应至少达到10万订单/秒")
    
    def test_data_model_field_types(self):
        """测试数据模型字段类型符合需求。"""
        # 测试Order模型字段类型
        order = Order(
            oid=18446744073709551615,  # uint64_t最大值
            account_id="ACC_001", 
            contract_id="T2303",
            direction=Direction.BID,
            price=99.99,
            volume=2147483647,  # int32_t最大值
            timestamp=1699999999999999999  # 纳秒时间戳
        )
        
        self.assertIsInstance(order.oid, int)
        self.assertIsInstance(order.account_id, str)
        self.assertIsInstance(order.contract_id, str)
        self.assertIsInstance(order.direction, Direction)
        self.assertIsInstance(order.price, float)
        self.assertIsInstance(order.volume, int)
        self.assertIsInstance(order.timestamp, int)
        
        # 测试Trade模型字段类型
        trade = Trade(
            tid=18446744073709551615,
            oid=18446744073709551615,
            price=99.99,
            volume=2147483647,
            timestamp=1699999999999999999,
            account_id="ACC_001",
            contract_id="T2303"
        )
        
        self.assertIsInstance(trade.tid, int)
        self.assertIsInstance(trade.oid, int)
        self.assertIsInstance(trade.price, float)
        self.assertIsInstance(trade.volume, int)
        self.assertIsInstance(trade.timestamp, int)
        
        # 测试CancelOrder模型字段类型
        cancel = CancelOrder(
            cancel_id=18446744073709551615,
            oid=18446744073709551615,
            timestamp=1699999999999999999,
            account_id="ACC_001",
            contract_id="T2303",
            cancel_volume=1000
        )
        
        self.assertIsInstance(cancel.cancel_id, int)
        self.assertIsInstance(cancel.oid, int)
        self.assertIsInstance(cancel.timestamp, int)
        self.assertIsInstance(cancel.cancel_volume, int)


if __name__ == "__main__":
    unittest.main(verbosity=2)