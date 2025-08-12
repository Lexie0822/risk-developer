from __future__ import annotations

import time
import unittest

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


class RiskEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.account = "ACC_TEST"

    def test_order_rate_limit_trigger_and_resume(self) -> None:
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=10_000),
                order_rate_limit=OrderRateLimitRuleConfig(threshold=3, window_ns=1_000_000_000),
            )
        )
        ts = time.time_ns()
        actions = []
        for i in range(4):
            actions.extend(
                engine.ingest_order(
                    Order(
                        oid=i,
                        account_id=self.account,
                        contract_id="T2303",
                        direction=Direction.BID,
                        price=100.0,
                        volume=1,
                        timestamp=ts + i * 10_000_000,
                    )
                )
            )
        self.assertTrue(any(a.type.name == "SUSPEND_ORDERING" for a in actions))

        # move time forward beyond window to trigger resume
        actions2 = engine.ingest_order(
            Order(
                oid=999,
                account_id=self.account,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=ts + 1_500_000_000,  # >1s later
            )
        )
        self.assertTrue(any(a.type.name == "RESUME_ORDERING" for a in actions2))

    def test_volume_limit_and_daily_reset(self) -> None:
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=100, dimension=StatsDimension.ACCOUNT, reset_daily=True),
                order_rate_limit=None,
            )
        )
        ts = time.time_ns()
        # 2 trades of 60 -> 120 triggers
        for i in range(2):
            order = Order(
                oid=i,
                account_id=self.account,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=ts,
            )
            engine.ingest_order(order)
            trade = Trade(tid=i, oid=i, price=100.0, volume=60, timestamp=ts)
            acts = engine.ingest_trade(trade)
        self.assertTrue(any(a.type.name == "SUSPEND_ACCOUNT_TRADING" for a in acts))

        # Next day: should reset, next trade should not suspend immediately
        next_day = ts + 86_400_000_000_000
        order = Order(oid=99, account_id=self.account, contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=next_day)
        engine.ingest_order(order)
        acts2 = engine.ingest_trade(Trade(tid=99, oid=99, price=100.0, volume=60, timestamp=next_day))
        self.assertFalse(any(a.type.name == "SUSPEND_ACCOUNT_TRADING" for a in acts2))

    def test_hot_update(self) -> None:
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=1_000_000),
                order_rate_limit=OrderRateLimitRuleConfig(threshold=3, window_ns=1_000_000_000),
            )
        )
        ts = time.time_ns()
        # Update threshold to 1 to trigger faster
        engine.update_order_rate_limit(threshold=1)
        acts = []
        for i in range(2):
            acts.extend(
                engine.ingest_order(
                    Order(
                        oid=i,
                        account_id=self.account,
                        contract_id="T2303",
                        direction=Direction.BID,
                        price=100.0,
                        volume=1,
                        timestamp=ts + i,
                    )
                )
            )
        self.assertTrue(any(a.type.name == "SUSPEND_ORDERING" for a in acts))

    def test_persistence_roundtrip(self) -> None:
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=100, dimension=StatsDimension.ACCOUNT, reset_daily=True),
                order_rate_limit=None,
            )
        )
        ts = time.time_ns()
        # Generate state
        order = Order(oid=1, account_id=self.account, contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
        engine.ingest_order(order)
        engine.ingest_trade(Trade(tid=1, oid=1, price=100.0, volume=90, timestamp=ts))
        snap = engine.snapshot()

        # Restore to new engine
        engine2 = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=100, dimension=StatsDimension.ACCOUNT, reset_daily=True),
                order_rate_limit=None,
            )
        )
        engine2.restore(snap)
        # Next trade of 20 should trigger suspension (90 + 20 = 110)
        order2 = Order(oid=2, account_id=self.account, contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
        engine2.ingest_order(order2)
        acts = engine2.ingest_trade(Trade(tid=2, oid=2, price=100.0, volume=20, timestamp=ts))
        self.assertTrue(any(a.type.name == "SUSPEND_ACCOUNT_TRADING" for a in acts))


if __name__ == "__main__":
    unittest.main()