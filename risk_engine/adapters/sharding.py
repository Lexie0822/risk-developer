from __future__ import annotations

# 简易多进程分片消费器：按 key（一致性哈希）将事件路由到固定 worker 进程
# 适用场景：高并发低延迟，通过多核并行绕过 GIL，按账户/Key 提供有序性

import multiprocessing as mp
import os
import signal
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence, Tuple, Union

from ..models import Order, Trade

Event = Union[Order, Trade]


@dataclass(slots=True)
class ShardConfig:
    num_workers: int = max(2, os.cpu_count() or 2)
    queue_maxsize: int = 100_000
    shutdown_timeout_s: float = 5.0


def _worker_loop(worker_id: int, make_engine: Callable[[int], object], in_q: mp.Queue, action_sink: Optional[Callable] = None):
    engine = make_engine(worker_id)
    running = True
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    while running:
        try:
            evt = in_q.get()
            if evt is None:
                break
            if isinstance(evt, Order):
                getattr(engine, "on_order", engine.ingest_order)(evt)
            elif isinstance(evt, Trade):
                getattr(engine, "on_trade", engine.ingest_trade)(evt)
        except Exception as e:
            # 最小容错：打印并继续，生产中可接入告警
            print(f"[worker {worker_id}] error: {e}")
    # 清理


def run_sharded_engine(
    *,
    shard_config: ShardConfig,
    make_engine: Callable[[int], object],
    event_iter: Iterable[Event],
    key_fn: Callable[[Event], str],
) -> None:
    """按 key 对事件流进行分片并交由多个工作进程处理。

    - make_engine(worker_id) -> RiskEngine 实例
    - key_fn(evt) -> 用于路由的一致性 Key（如 account_id）
    - event_iter: 任意事件可迭代（生成器、Kafka 适配器、文件流）
    """

    num_workers = shard_config.num_workers
    queues = [mp.Queue(maxsize=shard_config.queue_maxsize) for _ in range(num_workers)]
    procs: list[mp.Process] = []

    for wid in range(num_workers):
        p = mp.Process(target=_worker_loop, args=(wid, make_engine, queues[wid], None), daemon=True)
        p.start()
        procs.append(p)

    try:
        for evt in event_iter:
            k = key_fn(evt)
            idx = (hash(k) & 0x7FFFFFFF) % num_workers
            queues[idx].put(evt)
    finally:
        # 优雅关闭
        for q in queues:
            q.put(None)
        deadline = time.time() + shard_config.shutdown_timeout_s
        for p in procs:
            remaining = max(0.0, deadline - time.time())
            p.join(remaining)
        for p in procs:
            if p.is_alive():
                p.terminate()