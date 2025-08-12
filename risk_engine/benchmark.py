from __future__ import annotations

import random
import time
from typing import List

try:
    import uvloop  # type: ignore
except Exception:  # pragma: no cover
    uvloop = None

from .config import build_config
from .engine import RiskEngine
from .models import Direction, Order, Trade


def run_demo() -> None:
    cfg = build_config(
        {
            "contract_to_product": {"T2303": "T10Y", "T2306": "T10Y"},
            "rules": [
                {"type": "OrderRateLimitRule", "threshold": 5, "window_ns": 1_000_000_000},
                {"type": "AccountVolumeLimitRule", "daily_cap": 1000, "dimensions": ["account", "product"]},
            ],
        }
    )

    engine = RiskEngine(rules=cfg.rules, contract_to_product=cfg.contract_to_product)

    account = "ACC_001"
    now = time.time_ns()
    # Blast a handful of orders to trigger rate limit
    for i in range(7):
        o = Order(
            oid=i + 1,
            account_id=account,
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=now + i * 10_000_000,  # 10ms apart
        )
        actions = engine.process_order(o)
        for a in actions:
            print(a)

    # Create trades to grow daily volume
    cum = 0
    tid = 1
    while cum <= 1010:
        cum += 250
        t = Trade(tid=tid, oid=tid, price=100.0, volume=250, timestamp=time.time_ns())
        tid += 1
        actions = engine.process_trade(t)
        for a in actions:
            print(a)


def micro_benchmark(num_events: int = 200_000) -> None:
    if uvloop is not None:
        try:
            uvloop.install()
        except Exception:
            pass
    cfg = build_config(
        {
            "contract_to_product": {"T2303": "T10Y"},
            "rules": [
                {"type": "OrderRateLimitRule", "threshold": 500, "window_ns": 1_000_000_000},
                {"type": "AccountVolumeLimitRule", "daily_cap": 10_000, "dimensions": ["account"]},
            ],
        }
    )
    engine = RiskEngine(rules=cfg.rules, contract_to_product=cfg.contract_to_product)

    accounts = [f"ACC_{i:03d}" for i in range(50)]
    now = time.time_ns()
    orders: List[Order] = []
    for i in range(num_events):
        acc = accounts[i % len(accounts)]
        orders.append(
            Order(
                oid=i + 1,
                account_id=acc,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=now + i * 1000,  # 1 microsecond step
            )
        )

    t0 = time.perf_counter()
    count_actions = 0
    for o in orders:
        count_actions += len(engine.process_order(o))
    t1 = time.perf_counter()
    elapsed = t1 - t0
    throughput = num_events / elapsed
    print(f"Processed {num_events} orders in {elapsed:.4f}s, ~{throughput:,.0f} events/s, actions={count_actions}")


if __name__ == "__main__":
    run_demo()
    micro_benchmark(300_000)