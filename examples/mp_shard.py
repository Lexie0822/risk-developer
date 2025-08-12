from __future__ import annotations

import time
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType
from risk_engine.adapters.sharding import run_sharded_engine, ShardConfig


def make_engine(_: int) -> RiskEngine:
    return RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX"},
            deduplicate_actions=True,
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="VOL-1e9", metric=MetricType.TRADE_VOLUME, threshold=1e9,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,), by_account=True, by_product=True,
            ),
            OrderRateLimitRule(
                rule_id="ORDER-1e9-1S", threshold=1_000_000_000, window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,), resume_actions=(Action.RESUME_ORDERING,),
            ),
        ],
        action_sink=lambda a, r, o: None,
    )


def gen_events(n: int):
    base_ts = 2_000_000_000_000_000_000
    for i in range(n):
        yield Order(i+1, f"ACC_{i%64}", "T2303", Direction.BID, 100.0, 1, base_ts)
        if (i % 4) == 0:
            yield Trade(i+1, i+1, 100.0, 1, base_ts, account_id=f"ACC_{i%64}", contract_id="T2303")


if __name__ == "__main__":
    t0 = time.perf_counter()
    run_sharded_engine(
        shard_config=ShardConfig(num_workers=4),
        make_engine=make_engine,
        event_iter=gen_events(200_000),
        key_fn=lambda e: e.account_id,
    )
    t1 = time.perf_counter()
    print(f"mp_shard processed in {t1 - t0:.3f}s")