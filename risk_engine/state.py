from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass
from time import time
from typing import Dict, Tuple, Optional, Iterable

from .metrics import MetricType
from .dimensions import DimensionKey


def _ns_to_day_id(ns_ts: int) -> int:
    """将纳秒时间戳转换为日序号（UTC天）。"""
    seconds = ns_ts // 1_000_000_000
    return int(seconds // 86_400)


class ShardedLockDict:
    """分片加锁的字典以减少高并发下的锁竞争。

    - 分片数量固定为 64（可根据 CPU 核数调整）。
    - get 操作无锁读取（尽量），写操作使用所在分片的细粒度锁。
    - 适合计数类热点 Key 的高并发写入。
    """

    __slots__ = ("_shards", "_locks", "_num_shards")

    def __init__(self, num_shards: int = 64) -> None:
        self._num_shards = num_shards
        self._shards: Tuple[Dict, ...] = tuple({} for _ in range(num_shards))
        self._locks: Tuple[threading.Lock, ...] = tuple(
            threading.Lock() for _ in range(num_shards)
        )

    def _index(self, key_hash: int) -> int:
        return key_hash & (self._num_shards - 1)

    def get(self, key, default=None):
        shard = self._shards[self._index(hash(key))]
        return shard.get(key, default)

    def incr(self, key, delta=1):
        idx = self._index(hash(key))
        shard = self._shards[idx]
        lock = self._locks[idx]
        with lock:
            shard[key] = shard.get(key, 0) + delta
            return shard[key]

    def add_to_mapping_value(self, key, inner_key, delta=1):
        idx = self._index(hash(key))
        shard = self._shards[idx]
        lock = self._locks[idx]
        with lock:
            inner = shard.get(key)
            if inner is None:
                inner = {}
                shard[key] = inner
            inner[inner_key] = inner.get(inner_key, 0) + delta
            return inner[inner_key]

    def get_mapping(self, key):
        shard = self._shards[self._index(hash(key))]
        return shard.get(key)


@dataclass(slots=True)
class MultiDimDailyCounter:
    """多维-按日聚合的指标累加器。

    key: DimensionKey
    day_id -> metric -> value
    """

    store: ShardedLockDict

    def add(self, key: DimensionKey, metric: MetricType, value: float, ns_ts: int) -> float:
        day_id = _ns_to_day_id(ns_ts)
        composite_key = (key, day_id)
        # 存储结构： (DimensionKey, day_id) -> {metric: value}
        return self.store.add_to_mapping_value(composite_key, metric, value)

    def get(self, key: DimensionKey, metric: MetricType, ns_ts: int) -> float:
        day_id = _ns_to_day_id(ns_ts)
        composite_key = (key, day_id)
        mapping = self.store.get_mapping(composite_key)
        if not mapping:
            return 0.0
        return float(mapping.get(metric, 0.0))


class RollingWindowCounter:
    """滑动窗口计数器（按秒桶）。

    - 使用固定大小的环形数组，桶粒度为 1 秒。
    - 支持动态调整窗口尺寸（需在规则层做迁移或重置）。
    - 线程安全：同一 Key 下使用分片锁保护更新。
    """

    __slots__ = ("_window_size", "_buckets", "_locks")

    def __init__(self, window_size_seconds: int) -> None:
        assert window_size_seconds >= 1
        self._window_size = window_size_seconds
        self._buckets: ShardedLockDict = ShardedLockDict()
        self._locks: ShardedLockDict = ShardedLockDict()

    def _current_second(self, ns_ts: int) -> int:
        return ns_ts // 1_000_000_000

    def add(self, key, ns_ts: int, delta: int = 1) -> int:
        current_sec = self._current_second(ns_ts)
        idx = current_sec % self._window_size
        shard_key = (key, idx)
        # 每个桶是一个 dict: {second: count}
        # 写入前需清理过期秒的桶
        lock = self._locks.get(shard_key)
        if lock is None:
            # 初始化锁对象占位
            self._locks.incr(shard_key, 0)
        # 清理与累加
        bucket_map = self._buckets.get_mapping(shard_key)
        if bucket_map is None:
            self._buckets.add_to_mapping_value(shard_key, current_sec, 0)
            bucket_map = self._buckets.get_mapping(shard_key)
        # 清理过期
        keys_to_del = [sec for sec in bucket_map.keys() if sec != current_sec]
        for sec in keys_to_del:
            # 将旧秒桶清理掉
            self._buckets.add_to_mapping_value(shard_key, sec, -bucket_map.get(sec, 0))
            # 直接删除旧 key，释放内存
            map_ref = self._buckets.get_mapping(shard_key)
            if map_ref and sec in map_ref:
                del map_ref[sec]
        # 累加当前秒
        return int(self._buckets.add_to_mapping_value(shard_key, current_sec, delta))

    def total(self, key, ns_ts: int) -> int:
        current_sec = self._current_second(ns_ts)
        total_value = 0
        for i in range(self._window_size):
            sec = current_sec - i
            idx = sec % self._window_size
            shard_key = (key, idx)
            bucket_map = self._buckets.get_mapping(shard_key)
            if not bucket_map:
                continue
            v = bucket_map.get(sec, 0)
            total_value += v
        return int(total_value)