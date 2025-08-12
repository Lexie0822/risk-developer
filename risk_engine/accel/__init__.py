"""加速模块门面。

优先导入原生加速版本（Cython/Rust），若不可用则回退到 Python 实现。
"""

from __future__ import annotations

try:  # pragma: no cover
    # 假设存在编译产物 risk_engine_accel (Cython/Rust) 提供相同类名
    from risk_engine_accel import ShardedLockDict as FastShardedLockDict  # type: ignore
    from risk_engine_accel import RollingWindowCounter as FastRollingWindowCounter  # type: ignore
except Exception:  # pragma: no cover
    FastShardedLockDict = None  # type: ignore
    FastRollingWindowCounter = None  # type: ignore

if FastShardedLockDict is None:
    # 回退到 Python 版本
    from ..state import ShardedLockDict as FastShardedLockDict  # type: ignore
    from ..state import RollingWindowCounter as FastRollingWindowCounter  # type: ignore

__all__ = ["FastShardedLockDict", "FastRollingWindowCounter"]