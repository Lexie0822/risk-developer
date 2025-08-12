from __future__ import annotations

import unittest

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


class E2EVerificationTests(unittest.TestCase):
    def test_deterministic_action_sequence(self) -> None:
        # Fixed config and timestamps to make the test deterministic
        engine = RiskEngine(
            RiskEngineConfig(
                volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=StatsDimension.ACCOUNT),
                order_rate_limit=OrderRateLimitRuleConfig(threshold=3, window_ns=1_000_000_000, dimension=StatsDimension.ACCOUNT),
            )
        )
        base_ts = 1_700_000_000_000_000_000  # arbitrary fixed ns epoch
        account = "ACC_E2E"

        # 1) Order rate limit: 4 orders within 1s -> suspend, then one >1s later -> resume
        order_actions = []
        for i in range(4):
            order_actions.extend(
                engine.ingest_order(
                    Order(
                        oid=10 + i,
                        account_id=account,
                        contract_id="T2303",
                        direction=Direction.BID,
                        price=100.0,
                        volume=1,
                        timestamp=base_ts + i * 100_000_000,  # 0,100,200,300 ms
                    )
                )
            )
        # Expect a single suspend action when processing the 4th order
        self.assertEqual(
            [a.type.name for a in order_actions],
            ["SUSPEND_ORDERING"],
        )

        # One order 1.5s later should trigger resume
        resume_actions = engine.ingest_order(
            Order(
                oid=99,
                account_id=account,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=base_ts + 1_500_000_000,
            )
        )
        self.assertEqual([a.type.name for a in resume_actions], ["RESUME_ORDERING"])

        # 2) Volume limit: two trades totalling 1100 > 1000 -> suspend account trading
        # Ensure related orders exist for trade correlation
        engine.ingest_order(
            Order(
                oid=200,
                account_id=account,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=base_ts,
            )
        )
        engine.ingest_order(
            Order(
                oid=201,
                account_id=account,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=base_ts,
            )
        )

        acts = []
        acts.extend(
            engine.ingest_trade(
                Trade(tid=300, oid=200, price=100.0, volume=600, timestamp=base_ts)
            )
        )
        acts.extend(
            engine.ingest_trade(
                Trade(tid=301, oid=201, price=100.0, volume=500, timestamp=base_ts)
            )
        )
        self.assertEqual([a.type.name for a in acts], ["SUSPEND_ACCOUNT_TRADING"])


if __name__ == "__main__":
    unittest.main()