import time
from risk_engine import RiskEngine, Order, Trade, Direction, EngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, Dimension


def ns():
    return time.time_ns()


def test_order_rate_limit_exceed_and_resume():
    cfg = EngineConfig(order_rate_limit=OrderRateLimitRuleConfig(threshold_per_window=5, window_ns=1_000_000_000, bucket_ns=50_000_000))
    engine = RiskEngine(cfg)
    account = "ACC_001"
    t = ns()
    actions = []
    for i in range(6):
        actions += list(engine.ingest_order(Order(oid=i+1, account_id=account, contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=t)))
    assert any(a.type.name == "SUSPEND_ACCOUNT_ORDERING" for a in actions)
    # advance time beyond window so it resumes
    t += 1_100_000_000
    actions = []
    actions += list(engine.ingest_order(Order(oid=100, account_id=account, contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=t)))
    assert any(a.type.name == "RESUME_ACCOUNT_ORDERING" for a in actions)


def test_volume_limit_account_product():
    cfg = EngineConfig(
        product_mapping={"T2303": "T", "T2306": "T"},
        volume_limit=VolumeLimitRuleConfig(threshold=100, dimension=Dimension.ACCOUNT_PRODUCT),
        order_rate_limit=None,
    )
    engine = RiskEngine(cfg)
    account = "ACC_001"
    # two contracts of same product should aggregate together
    o1 = Order(oid=1, account_id=account, contract_id="T2303", direction=Direction.BID, price=100.0, volume=1, timestamp=ns())
    o2 = Order(oid=2, account_id=account, contract_id="T2306", direction=Direction.BID, price=100.0, volume=1, timestamp=ns())
    engine.ingest_order(o1)
    engine.ingest_order(o2)

    actions = []
    actions += list(engine.ingest_trade(Trade(tid=1, oid=1, price=100.0, volume=60, timestamp=ns())))
    actions += list(engine.ingest_trade(Trade(tid=2, oid=2, price=100.0, volume=50, timestamp=ns())))

    assert any(a.type.name == "SUSPEND_ACCOUNT_TRADING" for a in actions)