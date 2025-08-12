import time
from risk_engine import RiskEngine, EngineConfig, Order, Trade, Direction, Action
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.metrics import MetricType


def null_sink(action, rule_id, obj):
    pass


def run_bench(num_events: int = 200_000):
    engine = RiskEngine(
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
        action_sink=null_sink,
    )
    base_ts = 2_000_000_000_000_000_000
    t0 = time.perf_counter()
    for i in range(num_events):
        ts = base_ts
        engine.on_order(Order(i+1, "ACC_001", "T2303", Direction.BID, 100.0, 1, ts))
        if (i % 4) == 0:
            engine.on_trade(Trade(tid=i+1, oid=i+1, account_id="ACC_001", contract_id="T2303", price=100.0, volume=1, timestamp=ts))
    t1 = time.perf_counter()
    dt = t1 - t0
    print(f"Processed {num_events} orders + {num_events//4} trades in {dt:.3f}s => {(num_events+num_events//4)/dt:.0f} evt/s")


if __name__ == "__main__":
    run_bench()