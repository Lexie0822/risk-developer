from __future__ import annotations

import time

from risk_engine import (
    RiskEngine,
    Order,
    Trade,
    Direction,
    EngineConfig,
    VolumeLimitRuleConfig,
    OrderRateLimitRuleConfig,
    Dimension,
)


def ns() -> int:
    return time.time_ns()


def test_order_rate_limit_trigger_and_resume() -> None:
    engine = RiskEngine(
        EngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=10_000),
            order_rate_limit=OrderRateLimitRuleConfig(threshold_per_window=3, window_ns=1_000_000_000, bucket_ns=50_000_000),
        )
    )
    ts = ns()
    actions = []
    for i in range(4):
        actions.extend(
            engine.ingest_order(
                Order(
                    oid=i,
                    account_id="ACC_TEST",
                    contract_id="T2303",
                    direction=Direction.BID,
                    price=100.0,
                    volume=1,
                    timestamp=ts + i * 10_000_000,
                )
            )
        )
    assert any(a.type.name == "SUSPEND_ACCOUNT_ORDERING" for a in actions)

    # move time forward beyond window to trigger resume
    actions2 = engine.ingest_order(
        Order(
            oid=999,
            account_id="ACC_TEST",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=ts + 1_500_000_000,  # >1s later
        )
    )
    assert any(a.type.name == "RESUME_ACCOUNT_ORDERING" for a in actions2)


def test_volume_limit_product_dimension() -> None:
    engine = RiskEngine(
        EngineConfig(
            product_mapping={"T2303": "T", "T2306": "T"},
            volume_limit=VolumeLimitRuleConfig(threshold=500, dimension=Dimension.ACCOUNT_PRODUCT),
            order_rate_limit=None,
        )
    )
    ts = ns()
    # 300 + 250 trades across two contracts of same product -> 550 > 500
    o1 = Order(oid=1, account_id="ACC_P", contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
    o2 = Order(oid=2, account_id="ACC_P", contract_id="T2306", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
    engine.ingest_order(o1)
    engine.ingest_order(o2)
    acts = []
    acts.extend(engine.ingest_trade(Trade(tid=1, oid=1, price=100.0, volume=300, timestamp=ts)))
    acts.extend(engine.ingest_trade(Trade(tid=2, oid=2, price=100.0, volume=250, timestamp=ts)))
    assert any(a.type.name == "SUSPEND_ACCOUNT_TRADING" for a in acts)


def test_hot_update() -> None:
    engine = RiskEngine(
        EngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=1_000_000),
            order_rate_limit=OrderRateLimitRuleConfig(threshold_per_window=3, window_ns=1_000_000_000, bucket_ns=50_000_000),
        )
    )
    ts = ns()
    # Update threshold to 1 to trigger faster
    engine.update_rate_limit(threshold=1)
    acts = []
    for i in range(2):
        acts.extend(
            engine.ingest_order(
                Order(
                    oid=i,
                    account_id="ACC_TEST",
                    contract_id="T2303",
                    direction=Direction.BID,
                    price=100.0,
                    volume=1,
                    timestamp=ts + i,
                )
            )
        )
    assert any(a.type.name == "SUSPEND_ACCOUNT_ORDERING" for a in acts)
