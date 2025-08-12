from __future__ import annotations

# 需安装 redis 并启动本地服务

from risk_engine.adapters.redis_state import RedisStateStore

if __name__ == "__main__":
    store = RedisStateStore()
    print("counter before:", store.get_counter("order", "ACC_001"))
    print("incr ->", store.incr_counter("order", "ACC_001"))
    print("in blacklist before:", store.in_blacklist("acct", "ACC_001"))
    store.add_blacklist("acct", "ACC_001", ttl_s=60)
    print("in blacklist after:", store.in_blacklist("acct", "ACC_001"))