from __future__ import annotations

# 可选 Redis 状态存储：共享计数/黑名单，支持跨进程扩展
# 依赖 redis-py（pip install redis）

from typing import Optional

try:
    import redis
except Exception:  # pragma: no cover
    redis = None  # type: ignore


class RedisStateStore:
    def __init__(self, url: str = "redis://localhost:6379/0", prefix: str = "risk") -> None:
        if redis is None:
            raise ImportError("redis not installed. pip install redis")
        self._r = redis.Redis.from_url(url)
        self._prefix = prefix

    def _k(self, *parts: str) -> str:
        return ":".join((self._prefix,) + parts)

    # 计数器
    def incr_counter(self, name: str, key: str, delta: int = 1) -> int:
        return int(self._r.hincrby(self._k("counter", name), key, delta))

    def get_counter(self, name: str, key: str) -> int:
        v = self._r.hget(self._k("counter", name), key)
        return int(v or 0)

    # 黑名单
    def add_blacklist(self, name: str, key: str, ttl_s: Optional[int] = None) -> None:
        k = self._k("blacklist", name)
        self._r.sadd(k, key)
        if ttl_s:
            self._r.expire(k, ttl_s)

    def in_blacklist(self, name: str, key: str) -> bool:
        return bool(self._r.sismember(self._k("blacklist", name), key))