import unittest
import time

from risk_engine import RiskEngine, EngineConfig, Cancel, Action
from risk_engine.rules import AccountTradeMetricLimitRule
from risk_engine.metrics import MetricType


class CollectSink:
    def __init__(self):
        self.records = []

    def __call__(self, action, rule_id, obj):
        self.records.append((action, rule_id, obj))


class TestCancelFunctionality(unittest.TestCase):
    def test_cancel_count_limit(self):
        """测试撤单量限制规则"""
        sink = CollectSink()
        engine = RiskEngine(
            EngineConfig(),
            rules=[
                AccountTradeMetricLimitRule(
                    rule_id="CANCEL_LIMIT_TEST",
                    metric=MetricType.CANCEL_COUNT,
                    threshold=5,  # 5次撤单阈值
                    actions=(Action.BLOCK_CANCEL,),
                    by_account=True,
                ),
            ],
            action_sink=sink,
        )

        base_ts = time.time_ns()
        account = "CANCEL_TEST_ACC"
        
        # 发送4次撤单，不应触发限制
        for i in range(4):
            cancel = Cancel(
                cid=i+1,
                oid=i+100,
                account_id=account,
                contract_id="TEST001",
                timestamp=base_ts + i * 1000
            )
            engine.on_cancel(cancel)
        
        # 此时应该没有动作被触发
        self.assertEqual(len(sink.records), 0)
        
        # 发送第5次撤单，应该触发限制
        cancel = Cancel(
            cid=5,
            oid=105,
            account_id=account,
            contract_id="TEST001",
            timestamp=base_ts + 5000
        )
        engine.on_cancel(cancel)
        
        # 应该触发一次 BLOCK_CANCEL 动作
        self.assertEqual(len(sink.records), 1)
        action, rule_id, obj = sink.records[0]
        self.assertEqual(action, Action.BLOCK_CANCEL)
        self.assertEqual(rule_id, "CANCEL_LIMIT_TEST")
        self.assertIsInstance(obj, Cancel)
        self.assertEqual(obj.account_id, account)

    def test_cancel_multi_dimension(self):
        """测试撤单的多维度统计"""
        sink = CollectSink()
        engine = RiskEngine(
            EngineConfig(
                contract_to_product={"TEST001": "PROD_A", "TEST002": "PROD_A"}
            ),
            rules=[
                # 按账户维度
                AccountTradeMetricLimitRule(
                    rule_id="CANCEL_BY_ACCOUNT",
                    metric=MetricType.CANCEL_COUNT,
                    threshold=10,
                    actions=(Action.BLOCK_CANCEL,),
                    by_account=True,
                ),
                # 按产品维度
                AccountTradeMetricLimitRule(
                    rule_id="CANCEL_BY_PRODUCT",
                    metric=MetricType.CANCEL_COUNT,
                    threshold=15,
                    actions=(Action.ALERT,),
                    by_account=True,
                    by_product=True,
                ),
            ],
            action_sink=sink,
        )

        base_ts = time.time_ns()
        account = "MULTI_DIM_ACC"
        
        # 在不同合约上撤单，但同属一个产品
        for i in range(12):
            contract = "TEST001" if i % 2 == 0 else "TEST002"
            cancel = Cancel(
                cid=i+1,
                oid=i+200,
                account_id=account,
                contract_id=contract,
                timestamp=base_ts + i * 1000
            )
            engine.on_cancel(cancel)
        
        # 应该触发两个规则
        # 第11次撤单触发账户维度限制（10次阈值）
        # 第16次撤单触发产品维度限制（15次阈值）
        triggered_rules = set(rule_id for _, rule_id, _ in sink.records)
        self.assertIn("CANCEL_BY_ACCOUNT", triggered_rules)
        
        # 再发送4次撤单达到产品维度阈值
        for i in range(12, 16):
            contract = "TEST001" if i % 2 == 0 else "TEST002"
            cancel = Cancel(
                cid=i+1,
                oid=i+200,
                account_id=account,
                contract_id=contract,
                timestamp=base_ts + i * 1000
            )
            engine.on_cancel(cancel)
        
        triggered_rules = set(rule_id for _, rule_id, _ in sink.records)
        self.assertIn("CANCEL_BY_PRODUCT", triggered_rules)

    def test_legacy_ingest_cancel(self):
        """测试旧版本接口的撤单处理"""
        engine = RiskEngine(
            EngineConfig(),
            rules=[
                AccountTradeMetricLimitRule(
                    rule_id="LEGACY_CANCEL_TEST",
                    metric=MetricType.CANCEL_COUNT,
                    threshold=3,
                    actions=(Action.BLOCK_CANCEL,),
                    by_account=True,
                ),
            ],
        )

        base_ts = time.time_ns()
        account = "LEGACY_ACC"
        
        # 使用旧版本 ingest_cancel 接口
        actions_list = []
        for i in range(4):
            cancel = Cancel(
                cid=i+1,
                oid=i+300,
                account_id=account,
                contract_id="LEGACY001",
                timestamp=base_ts + i * 1000
            )
            actions = engine.ingest_cancel(cancel)
            actions_list.extend(actions)
        
        # 第4次撤单应该触发限制
        self.assertTrue(len(actions_list) > 0)
        # 验证返回的动作对象有正确的属性
        triggered_action = actions_list[0]
        self.assertEqual(triggered_action.type, Action.BLOCK_CANCEL)
        self.assertEqual(triggered_action.account_id, account)

    def test_cancel_with_exchange_dimension(self):
        """测试按交易所维度的撤单统计"""
        sink = CollectSink()
        engine = RiskEngine(
            EngineConfig(
                contract_to_exchange={"SHFE001": "SHFE", "DCE001": "DCE"}
            ),
            rules=[
                AccountTradeMetricLimitRule(
                    rule_id="CANCEL_BY_EXCHANGE",
                    metric=MetricType.CANCEL_COUNT,
                    threshold=5,
                    actions=(Action.ALERT,),
                    by_account=True,
                    by_exchange=True,
                ),
            ],
            action_sink=sink,
        )

        base_ts = time.time_ns()
        account = "EXCHANGE_ACC"
        
        # 在SHFE交易所撤单
        for i in range(6):
            cancel = Cancel(
                cid=i+1,
                oid=i+400,
                account_id=account,
                contract_id="SHFE001",
                timestamp=base_ts + i * 1000,
                exchange_id="SHFE"
            )
            engine.on_cancel(cancel)
        
        # 应该触发按交易所维度的限制
        self.assertTrue(len(sink.records) > 0)
        action, rule_id, obj = sink.records[0]
        self.assertEqual(action, Action.ALERT)
        self.assertEqual(rule_id, "CANCEL_BY_EXCHANGE")


if __name__ == "__main__":
    unittest.main()