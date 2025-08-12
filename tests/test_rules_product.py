from __future__ import annotations

import time
import unittest

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


class ProductDimensionTests(unittest.TestCase):
    def test_volume_limit_by_product(self) -> None:
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=500, dimension=StatsDimension.PRODUCT),
                order_rate_limit=None,
                contract_to_product={"T2303": "T", "T2306": "T"},
            )
        )
        ts = time.time_ns()
        # Two different contracts under same product should aggregate
        order1 = Order(oid=1, account_id="ACC_P", contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
        order2 = Order(oid=2, account_id="ACC_P", contract_id="T2306", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
        engine.ingest_order(order1)
        engine.ingest_order(order2)
        acts = []
        acts.extend(engine.ingest_trade(Trade(tid=1, oid=1, price=100.0, volume=300, timestamp=ts)))
        acts.extend(engine.ingest_trade(Trade(tid=2, oid=2, price=100.0, volume=250, timestamp=ts)))  # total 550 > 500
        self.assertTrue(any(a.type.name == "SUSPEND_ACCOUNT_TRADING" for a in acts))

    def test_order_rate_limit_by_product(self) -> None:
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=None,
                order_rate_limit=OrderRateLimitRuleConfig(threshold=3, window_ns=1_000_000_000, dimension=StatsDimension.PRODUCT),
                contract_to_product={"T2303": "T", "T2306": "T"},
            )
        )
        ts = time.time_ns()
        actions = []
        # 4 orders within window across T2303 and T2306 should count together
        orders = [
            Order(oid=i, account_id="ACC_P", contract_id="T2303" if i % 2 == 0 else "T2306", direction=Direction.BID, price=100.0, volume=1, timestamp=ts + i)
            for i in range(4)
        ]
        for o in orders:
            actions.extend(engine.ingest_order(o))
        self.assertTrue(any(a.type.name == "SUSPEND_ORDERING" for a in actions))


if __name__ == "__main__":
    unittest.main()