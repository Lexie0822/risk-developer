from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


def read_orders(path: Path) -> Iterable[Order]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield Order(
                oid=int(row["oid"]),
                account_id=row["account_id"],
                contract_id=row["contract_id"],
                direction=Direction(row["direction"]),
                price=float(row["price"]),
                volume=int(row["volume"]),
                timestamp=int(row["timestamp"]),
            )


def read_trades(path: Path) -> Iterable[Trade]:
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield Trade(
                tid=int(row["tid"]),
                oid=int(row["oid"]),
                price=float(row["price"]),
                volume=int(row["volume"]),
                timestamp=int(row["timestamp"]),
            )


def main() -> None:
    ap = argparse.ArgumentParser(description="Replay CSV orders and trades through the risk engine")
    ap.add_argument("--orders", type=Path, default=Path(__file__).with_name("data").joinpath("sample_orders.csv"))
    ap.add_argument("--trades", type=Path, default=Path(__file__).with_name("data").joinpath("sample_trades.csv"))
    ap.add_argument("--product-map", type=Path, default=Path(__file__).with_name("data").joinpath("contract_to_product.csv"))
    ap.add_argument("--out", type=Path, default=Path("reports/replay_actions.jsonl"))
    ap.add_argument("--order-threshold", type=int, default=3)
    ap.add_argument("--order-window-ns", type=int, default=1_000_000_000)
    ap.add_argument("--volume-threshold", type=int, default=1000)
    args = ap.parse_args()

    # Load product mapping
    mapping: Dict[str, str] = {}
    if args.product_map.exists():
        with args.product_map.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                mapping[row["contract_id"]] = row["product_id"]

    engine = RiskEngine(
        RiskEngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=args.volume_threshold, dimension=StatsDimension.ACCOUNT),
            order_rate_limit=OrderRateLimitRuleConfig(threshold=args.order_threshold, window_ns=args.order_window_ns, dimension=StatsDimension.ACCOUNT),
            contract_to_product=mapping,
        )
    )

    actions: List[str] = []
    for o in read_orders(args.orders):
        for a in engine.ingest_order(o):
            actions.append(a.short())
            print(a.short())

    for t in read_trades(args.trades):
        for a in engine.ingest_trade(t):
            actions.append(a.short())
            print(a.short())

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for line in actions:
            f.write(line + "\n")

    print(f"Wrote actions to {args.out}")


if __name__ == "__main__":
    main()