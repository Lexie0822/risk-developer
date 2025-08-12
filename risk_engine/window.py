from __future__ import annotations
from typing import Dict, Tuple, List


class RingBucketCounter:
    """Fixed-size ring buffer buckets per key.

    Designed for high-rate increments and queries in nanosecond time.
    """

    __slots__ = (
        "window_ns",
        "bucket_ns",
        "num_buckets",
        "_state",
    )

    def __init__(self, window_ns: int, bucket_ns: int) -> None:
        assert window_ns % bucket_ns == 0, "window must be multiple of bucket"
        self.window_ns = window_ns
        self.bucket_ns = bucket_ns
        self.num_buckets = window_ns // bucket_ns
        # key -> (start_bucket_index, start_bucket_time, values[list])
        self._state: Dict[str, Tuple[int, int, List[int]]] = {}

    def _ensure_key(self, key: str, now_ns: int) -> Tuple[int, int, List[int]]:
        bucket_idx = (now_ns // self.bucket_ns) % self.num_buckets
        bucket_time = now_ns - (now_ns % self.bucket_ns)
        if key not in self._state:
            self._state[key] = (bucket_idx, bucket_time, [0] * self.num_buckets)
            return self._state[key]
        start_idx, start_time, values = self._state[key]
        # Advance buckets if time moved forward
        delta_buckets = (bucket_time - start_time) // self.bucket_ns
        if delta_buckets >= self.num_buckets:
            # Full window elapsed, reset all
            self._state[key] = (bucket_idx, bucket_time, [0] * self.num_buckets)
            return self._state[key]
        while delta_buckets > 0:
            # zero-out the next bucket in ring
            start_idx = (start_idx + 1) % self.num_buckets
            values[start_idx] = 0
            start_time += self.bucket_ns
            delta_buckets -= 1
        self._state[key] = (start_idx, start_time, values)
        return self._state[key]

    def add(self, key: str, value: int, now_ns: int) -> None:
        start_idx, start_time, values = self._ensure_key(key, now_ns)
        bucket_idx = (now_ns // self.bucket_ns) % self.num_buckets
        values[bucket_idx] += value

    def sum(self, key: str, now_ns: int) -> int:
        if key not in self._state:
            return 0
        start_idx, start_time, values = self._ensure_key(key, now_ns)
        return sum(values)

    def reset_key(self, key: str) -> None:
        if key in self._state:
            start_idx, start_time, values = self._state[key]
            for i in range(self.num_buckets):
                values[i] = 0