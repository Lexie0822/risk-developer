from __future__ import annotations

import time

from risk_engine.actions import Action
from risk_engine.config import RiskEngineConfig, OrderRateLimitRuleConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


def ns_now() -> int:
    return time.time_ns()


def main() -> None:
    config = RiskEngineConfig(
        volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=StatsDimension.ACCOUNT),
        order_rate_limit=OrderRateLimitRuleConfig(threshold=5, window_ns=1_000_000_000),
        contract_to_product={"T2303": "T", "T2306": "T"},
    )
    engine = RiskEngine(config)

    account = "ACC_001"

    # Burst of orders to trigger rate limit
    base_ts = ns_now()
    actions = []
    for i in range(7):
        order = Order(
            oid=1000 + i,
            account_id=account,
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0 + i,
            volume=1,
            timestamp=base_ts + i * 10_000_000,  # 10ms apart
        )
        actions.extend(engine.ingest_order(order))

    # Show actions from rate limit
    print("Rate-limit actions:")
    for act in actions:
        print("  ", act.short())

    # Trades to exceed volume limit
    actions2 = []
    # Assume all trades relate to the last order id for simplicity
    cumulative = 0
    for i in range(5):
        trade = Trade(
            tid=2000 + i,
            oid=1000 + i,
            price=100.0 + i,
            volume=300,  # 5 * 300 = 1500 > 1000 threshold
            timestamp=ns_now(),
        )
        cumulative += trade.volume
        actions2.extend(engine.ingest_trade(trade))

    print("\nVolume-limit actions:")
    for act in actions2:
        print("  ", act.short())


if __name__ == "__main__":
    main()