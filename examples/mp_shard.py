from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
import time
from dataclasses import asdict
from typing import List, Tuple

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


def shard_for_account(account_id: str, num_shards: int) -> int:
    h = hashlib.blake2b(account_id.encode(), digest_size=2).digest()
    return int.from_bytes(h, "little") % num_shards


def worker(shard_id: int, in_q: mp.Queue, out_q: mp.Queue) -> None:
    engine = RiskEngine(
        RiskEngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=StatsDimension.ACCOUNT),
            order_rate_limit=OrderRateLimitRuleConfig(threshold=50, window_ns=1_000_000_000),
            contract_to_product={"T2303": "T"},
        )
    )
    while True:
        msg = in_q.get()
        if msg is None:
            break
        typ, payload = msg
        if typ == "order":
            actions = engine.ingest_order(Order(**payload))
        else:
            actions = engine.ingest_trade(Trade(**payload))
        for a in actions:
            out_q.put(a.short())
    out_q.put({"shard": shard_id, "status": "done"})


def demo(num_shards: int = 2) -> None:
    in_queues = [mp.Queue(maxsize=10_000) for _ in range(num_shards)]
    out_q = mp.Queue()
    procs = [mp.Process(target=worker, args=(i, in_queues[i], out_q)) for i in range(num_shards)]
    for p in procs:
        p.start()

    # Feed data sharded by account
    ts = time.time_ns()
    for i in range(200):
        acc = f"ACC_{i % 4}"
        shard = shard_for_account(acc, num_shards)
        in_queues[shard].put((
            "order",
            dict(
                oid=i,
                account_id=acc,
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=ts + i,
            ),
        ))

    # Signal finish
    for q in in_queues:
        q.put(None)

    # Collect a few outputs
    done = 0
    while done < num_shards:
        m = out_q.get()
        if isinstance(m, dict) and m.get("status") == "done":
            done += 1
        else:
            print("Action:", m)

    for p in procs:
        p.join()


if __name__ == "__main__":
    demo()