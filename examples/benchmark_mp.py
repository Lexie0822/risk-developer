from __future__ import annotations

import multiprocessing as mp
import os
import time
from typing import Tuple

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


def worker(proc_idx: int, num_orders: int, num_trades: int, result_q: mp.Queue) -> None:
    engine = RiskEngine(
        RiskEngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=10_000_000, dimension=StatsDimension.ACCOUNT),
            order_rate_limit=OrderRateLimitRuleConfig(threshold=1_000_000, window_ns=1_000_000_000),
            contract_to_product={"T2303": "T"},
        )
    )
    ts = time.time_ns()

    t0 = time.perf_counter()
    for i in range(num_orders):
        engine.ingest_order(
            Order(
                oid=(proc_idx << 48) + i,
                account_id=f"ACC_{i % 64}",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=ts + i,
            )
        )
    t1 = time.perf_counter()

    for i in range(num_trades):
        engine.ingest_trade(
            Trade(
                tid=(proc_idx << 48) + i,
                oid=(proc_idx << 48) + i,
                price=100.0,
                volume=1,
                timestamp=ts + i,
            )
        )
    t2 = time.perf_counter()

    result_q.put((num_orders / (t1 - t0), num_trades / (t2 - t1)))


def run(num_procs: int = max(2, os.cpu_count() or 2), num_orders: int = 200_000, num_trades: int = 100_000) -> None:
    ctx = mp.get_context("fork")
    result_q: mp.Queue = ctx.Queue()
    procs = [
        ctx.Process(target=worker, args=(i, num_orders, num_trades, result_q)) for i in range(num_procs)
    ]
    for p in procs:
        p.start()
    order_rates = []
    trade_rates = []
    for _ in procs:
        o, t = result_q.get()
        order_rates.append(o)
        trade_rates.append(t)
    for p in procs:
        p.join()

    total_orders_per_sec = int(sum(order_rates))
    total_trades_per_sec = int(sum(trade_rates))
    print(f"Processes: {num_procs}")
    print(f"Aggregated order throughput: ~{total_orders_per_sec}/s")
    print(f"Aggregated trade throughput: ~{total_trades_per_sec}/s")


if __name__ == "__main__":
    run()