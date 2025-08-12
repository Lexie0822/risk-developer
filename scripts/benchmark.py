import time
from risk_engine import RiskEngine, Order, Trade, Direction, EngineConfig, OrderRateLimitRuleConfig


def bench(num_orders: int = 1_000_000):
    cfg = EngineConfig(order_rate_limit=OrderRateLimitRuleConfig(threshold_per_window=1_000_000, window_ns=1_000_000_000, bucket_ns=1_000_000))
    engine = RiskEngine(cfg)

    t0 = time.perf_counter_ns()
    ts = time.time_ns()
    for i in range(num_orders):
        o = Order(oid=i, account_id="A", contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=ts)
        engine.ingest_order(o)
        ts += 1000
    t1 = time.perf_counter_ns()
    elapsed_s = (t1 - t0) / 1e9
    rate = num_orders / elapsed_s
    print(f"orders: {num_orders}, time: {elapsed_s:.3f}s, rate: {rate/1e6:.2f} M/s")


if __name__ == "__main__":
    bench()