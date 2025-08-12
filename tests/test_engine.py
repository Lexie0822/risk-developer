import unittest
import time

from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType


class CollectSink:
    def __init__(self):
        self.records = []

    def __call__(self, action, rule_id, obj):
        self.records.append((action, rule_id, obj))


class TestRiskEngine(unittest.TestCase):
    def make_engine(self):
        sink = CollectSink()
        engine = RiskEngine(
            EngineConfig(
                contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
                contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
                deduplicate_actions=True,
            ),
            rules=[
                AccountTradeMetricLimitRule(
                    rule_id="VOL-1000", metric=MetricType.TRADE_VOLUME, threshold=1000,
                    actions=(Action.SUSPEND_ACCOUNT_TRADING,), by_account=True, by_product=True,
                ),
                OrderRateLimitRule(
                    rule_id="ORDER-50-1S", threshold=5, window_seconds=1,
                    suspend_actions=(Action.SUSPEND_ORDERING,), resume_actions=(Action.RESUME_ORDERING,),
                ),
            ],
            action_sink=sink,
        )
        return engine, sink

    def test_trade_volume_limit(self):
        engine, sink = self.make_engine()
        base_ts = 1_700_000_000_000_000_000
        # 990 手 -> 不触发
        engine.on_trade(Trade(tid=1, oid=1, account_id="ACC_001", contract_id="T2303", price=100.0, volume=990, timestamp=base_ts))
        self.assertFalse(any(a for a, _, _ in sink.records if a == Action.SUSPEND_ACCOUNT_TRADING))
        # +10 手 -> 达阈值触发
        engine.on_trade(Trade(tid=2, oid=2, account_id="ACC_001", contract_id="T2306", price=101.0, volume=10, timestamp=base_ts + 1))
        self.assertTrue(any(a for a, _, _ in sink.records if a == Action.SUSPEND_ACCOUNT_TRADING))

    def test_order_rate_limit_suspend_and_resume(self):
        engine, sink = self.make_engine()
        base_ts = 1_800_000_000_000_000_000
        # 6 笔单在 1s 内，超过阈值 5 -> 触发暂停
        for i in range(6):
            engine.on_order(Order(i+1, "ACC_001", "T2303", Direction.BID, 100.0, 1, base_ts))
        self.assertTrue(any(a for a, _, _ in sink.records if a == Action.SUSPEND_ORDERING))
        # 下一秒 1 笔 -> 计数回落，应触发恢复
        engine.on_order(Order(100, "ACC_001", "T2303", Direction.BID, 100.0, 1, base_ts + 1_000_000_000))
        self.assertTrue(any(a for a, _, _ in sink.records if a == Action.RESUME_ORDERING))

    def test_product_dimension_aggregation(self):
        engine, sink = self.make_engine()
        base_ts = 1_900_000_000_000_000_000
        # 同产品（T10Y）不同合约的成交，应在产品维度汇总
        engine.on_trade(Trade(tid=1, oid=1, account_id="ACC_002", contract_id="T2303", price=100.0, volume=600, timestamp=base_ts))
        engine.on_trade(Trade(tid=2, oid=2, account_id="ACC_002", contract_id="T2306", price=100.0, volume=400, timestamp=base_ts + 1))
        # +1 手 -> 达阈值
        engine.on_trade(Trade(tid=3, oid=3, account_id="ACC_002", contract_id="T2306", price=100.0, volume=1, timestamp=base_ts + 2))
        self.assertTrue(any(a for a, _, _ in sink.records if a == Action.SUSPEND_ACCOUNT_TRADING))


if __name__ == "__main__":
    unittest.main()