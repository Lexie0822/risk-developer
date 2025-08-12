## Realtime Risk Control Module (Python)

This project implements a pluggable, low-latency risk-control engine for high-frequency trading streams. It consumes `Order` and `Trade` events, evaluates rules, and emits `Action` decisions (pause/resume).

### Key features
- **Pluggable rules**: add new rules by subclassing `BaseRule`.
- **Two built-in rules**:
  - **OrderRateLimitRule**: sliding-window rate limiter per account.
  - **AccountVolumeLimitRule**: daily trade volume cap with multi-dimensional statistics (account/contract/product).
- **Extensible dimensions**: contract→product mapping provided via config.
- **Low-latency data path**: slot dataclasses, lock-free deques, sharded maps, minimal allocations.
- **Event-time API**: processes nanosecond timestamps and periodic `tick()` for time-driven resumption.

### Install
Optional dependency `uvloop` (Linux/macOS) can improve latency.

```bash
python -m risk_engine.benchmark | cat
```

### Quick start
```python
from risk_engine import RiskEngine, Order, Trade, Direction
from risk_engine.config import build_config

cfg = build_config({
  "contract_to_product": {"T2303": "T10Y", "T2306": "T10Y"},
  "rules": [
    {"type": "OrderRateLimitRule", "threshold": 50, "window_ns": 1_000_000_000},
    {"type": "AccountVolumeLimitRule", "daily_cap": 1000, "dimensions": ["account", "product"]},
  ],
})
engine = RiskEngine(rules=cfg.rules, contract_to_product=cfg.contract_to_product)
```

Send events:
```python
actions = engine.process_order(order)
actions = engine.process_trade(trade)
actions = engine.tick()  # optional periodic resume checks
```

### Configuration (API/Interface)
- `contract_to_product`: map `contract_id` to `product_id` to enable product-level statistics.
- `rules`: list of rule definitions:
  - `OrderRateLimitRule`: `{ "type": "OrderRateLimitRule", "threshold": 50, "window_ns": 1_000_000_000, "bucket_ns": 1_000_000 }`
  - `AccountVolumeLimitRule`: `{ "type": "AccountVolumeLimitRule", "daily_cap": 1000, "dimensions": ["account", "product"] }`

These two cover the interview requirements and are extensible by adding new rule classes.

### Architecture for high throughput and low latency
- **Single-writer event loop**: keep critical path single-threaded to avoid locks. Integrates with async I/O (Kafka/Redis) if needed.
- **Cache-friendly structures**: `dataclass(slots=True)`, ring-deque sliding counters with fixed buckets, integer math only on the hot path.
- **Indexing**: `oid → (account, contract)` to enrich trades without DB lookups.
- **Backpressure**: rate rule returns `PAUSE_ORDER` which can be used to reject orders at the edge.
- **Zero-copy serialization**: out of scope here, but wire adapters should use `msgpack`/`Cap’n Proto` or shared memory.

### Expected performance (local micro-benchmark)
The included benchmark generates 300k orders and processes them in a tight loop. On a typical modern laptop, the engine achieves hundreds of thousands to low millions of events/sec in CPython. Results vary by CPU and Python version.

For sustained multi-million events/sec with microsecond p99 latency, integrate one of the following accelerations (drop-in with this design):
- Run under **PyPy** or **CPython + uvloop** for faster event loop (already supported).
- Replace hot counters with a small **Rust/Cython** extension (same rule interfaces).
- Use **affinity and hugepages**; pin the process and disable GC in hot windows.

### Advantages
- Minimal GC pressure, lock-free data path, explicit time-window logic.
- Clear interfaces for adding rules and dimensions.
- Works in-process or behind a microservice boundary.

### Limitations
- Pure Python cannot guarantee true microsecond latency under all loads. For the strictest SLAs, compile the counters to native code (Rust/Cython) and pin the process.
- This demo uses in-memory state; you must add checkpointing if you require recovery.
- `AccountVolumeLimitRule` pauses until manual reset (`reset_daily()`); schedule resets at session/day boundaries as needed.
