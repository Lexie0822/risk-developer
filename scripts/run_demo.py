import random
import time
from risk_engine import RiskEngine, Order, Trade, Direction, EngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, Dimension


def now_ns():
    return time.time_ns()


def main():
    cfg = EngineConfig(
        product_mapping={"T2303": "T", "T2306": "T"},
        volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=Dimension.ACCOUNT_PRODUCT),
        order_rate_limit=OrderRateLimitRuleConfig(threshold_per_window=50, window_ns=1_000_000_000, bucket_ns=10_000_000),
    )
    engine = RiskEngine(cfg)

    account = "ACC_001"
    contract = "T2303"

    actions = []

    # Simulate order burst
    for i in range(60):
        o = Order(
            oid=i + 1,
            account_id=account,
            contract_id=contract,
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=now_ns(),
        )
        actions.extend(engine.ingest_order(o))

    # Simulate trades to hit volume threshold
    traded = 0
    tid = 1
    while traded < 1100:
        tr = Trade(tid=tid, oid=random.randint(1, 60), price=100.0, volume=50, timestamp=now_ns())
        traded += tr.volume
        tid += 1
        actions.extend(engine.ingest_trade(tr))

    for a in actions:
        print(a)


if __name__ == "__main__":
    main()