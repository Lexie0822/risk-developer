from __future__ import annotations

import io
import json
import os
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from risk_engine.config import OrderRateLimitRuleConfig, RiskEngineConfig, VolumeLimitRuleConfig
from risk_engine.engine import RiskEngine
from risk_engine.models import Direction, Order, Trade
from risk_engine.stats import StatsDimension


def run_tests_collect_output() -> Dict[str, Any]:
    loader = unittest.TestLoader()
    suite = loader.discover("tests")
    stream = io.StringIO()
    runner = unittest.TextTestRunner(stream=stream, verbosity=2)
    result = runner.run(suite)
    stream_text = stream.getvalue()
    return {
        "testsRun": result.testsRun,
        "failures": [(case.id(), str(tb)) for case, tb in result.failures],
        "errors": [(case.id(), str(tb)) for case, tb in result.errors],
        "skipped": [(case.id(), reason) for case, reason in getattr(result, "skipped", [])],
        "ok": result.wasSuccessful(),
        "raw_output": stream_text,
    }


def run_demo_actions() -> Dict[str, Any]:
    config = RiskEngineConfig(
        volume_limit=VolumeLimitRuleConfig(threshold=1000, dimension=StatsDimension.ACCOUNT),
        order_rate_limit=OrderRateLimitRuleConfig(threshold=5, window_ns=1_000_000_000),
        contract_to_product={"T2303": "T", "T2306": "T"},
    )
    engine = RiskEngine(config)

    account = "ACC_001"

    base_ts = time.time_ns()
    actions_rate: List[str] = []
    for i in range(7):
        order = Order(
            oid=1000 + i,
            account_id=account,
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0 + i,
            volume=1,
            timestamp=base_ts + i * 10_000_000,
        )
        for a in engine.ingest_order(order):
            actions_rate.append(a.short())

    actions_volume: List[str] = []
    for i in range(5):
        trade = Trade(
            tid=2000 + i,
            oid=1000 + i,
            price=100.0 + i,
            volume=300,
            timestamp=time.time_ns(),
        )
        for a in engine.ingest_trade(trade):
            actions_volume.append(a.short())

    return {
        "rate_limit_actions": actions_rate,
        "volume_limit_actions": actions_volume,
    }


def run_benchmark(num_orders: int = 200_000, num_trades: int = 100_000) -> Dict[str, Any]:
    engine = RiskEngine(
        RiskEngineConfig(
            volume_limit=VolumeLimitRuleConfig(threshold=10_000_000, dimension=StatsDimension.ACCOUNT),
            order_rate_limit=OrderRateLimitRuleConfig(threshold=1_000_000, window_ns=1_000_000_000),
            contract_to_product={"T2303": "T"},
        )
    )

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

    order_tps = int(num_orders / (t1 - t0)) if t1 > t0 else 0
    trade_tps = int(num_trades / (t2 - t1)) if t2 > t1 else 0

    return {
        "num_orders": num_orders,
        "num_trades": num_trades,
        "orders_seconds": round(t1 - t0, 6),
        "trades_seconds": round(t2 - t1, 6),
        "orders_tps": order_tps,
        "trades_tps": trade_tps,
    }


def write_reports(data: Dict[str, Any]) -> Dict[str, str]:
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    json_path = out_dir / "report.json"

    # Markdown
    md_lines = []
    md_lines.append(f"# 风控模块测试与性能报告\n")
    md_lines.append(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}\n\n")

    t = data["tests"]
    md_lines.append("## 测试结果\n")
    md_lines.append(f"- 是否全部通过: {'是' if t['ok'] else '否'}\n")
    md_lines.append(f"- 用例总数: {t['testsRun']}\n")
    md_lines.append(f"- 失败: {len(t['failures'])}, 错误: {len(t['errors'])}, 跳过: {len(t['skipped'])}\n\n")
    md_lines.append("<details><summary>测试输出</summary>\n\n")
    md_lines.append("```")
    md_lines.append(t["raw_output"].strip())
    md_lines.append("```\n\n</details>\n\n")

    d = data["demo"]
    md_lines.append("## 演示触发的 Action\n")
    md_lines.append("- 限频规则触发:\n")
    for s in d["rate_limit_actions"]:
        md_lines.append(f"  - {s}\n")
    md_lines.append("- 成交量规则触发:\n")
    for s in d["volume_limit_actions"]:
        md_lines.append(f"  - {s}\n")
    md_lines.append("\n")

    b = data["benchmark"]
    md_lines.append("## 性能基准\n")
    md_lines.append(f"- Orders: {b['num_orders']} 条，耗时 {b['orders_seconds']} s，吞吐 ~{b['orders_tps']}/s\n")
    md_lines.append(f"- Trades: {b['num_trades']} 条，耗时 {b['trades_seconds']} s，吞吐 ~{b['trades_tps']}/s\n")

    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    # JSON
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"markdown": str(md_path), "json": str(json_path)}


def main() -> None:
    tests = run_tests_collect_output()
    demo = run_demo_actions()
    bench = run_benchmark()
    paths = write_reports({"tests": tests, "demo": demo, "benchmark": bench})
    print(json.dumps({"ok": tests["ok"], "paths": paths}, ensure_ascii=False))


if __name__ == "__main__":
    main()