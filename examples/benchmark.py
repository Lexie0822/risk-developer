from __future__ import annotations

import time
from typing import List

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


def run_benchmark(num_orders: int = 200_000, num_trades: int = 100_000) -> None:
    engine = RiskEngine(
        RiskEngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=10_000_000, dimension=StatsDimension.ACCOUNT),
            order_rate_limit=OrderRateLimitRuleConfig(threshold=1_000_000, window_ns=1_000_000_000),
            contract_to_product={"T2303": "T"},
        )
    )

    # Orders
    t0 = time.perf_counter()
    ts = time.time_ns()
    for i in range(num_orders):
        engine.ingest_order(
            Order(
                oid=i,
                account_id=f"ACC_{i % 32}",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=ts + i,
            )
        )
    t1 = time.perf_counter()

    # Trades
    for i in range(num_trades):
        engine.ingest_trade(
            Trade(
                tid=i,
                oid=i,
                price=100.0,
                volume=1,
                timestamp=ts + i,
            )
        )
    t2 = time.perf_counter()

    order_tps = int(num_orders / (t1 - t0))
    trade_tps = int(num_trades / (t2 - t1))
    print(f"Orders: {num_orders} in {t1 - t0:.3f}s -> ~{order_tps}/s")
    print(f"Trades: {num_trades} in {t2 - t1:.3f}s -> ~{trade_tps}/s")


if __name__ == "__main__":
    run_benchmark()