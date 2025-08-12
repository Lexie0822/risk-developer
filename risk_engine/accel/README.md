# 加速实现指南

本目录描述如何用 Cython 或 Rust(PyO3) 将热点结构下沉为原生实现。

## Cython
- 目标：实现 `ShardedLockDict` 与 `RollingWindowCounter` 的无 GIL/原子操作版本。
- 参考结构：
  - `risk_engine_accel/__init__.py` 暴露同名类
  - 编译产物名：`risk_engine_accel`
- 示例 pyproject.toml
```toml
[build-system]
requires = ["setuptools", "wheel", "cython"]
build-backend = "setuptools.build_meta"
```
- 示例 setup.cfg（或 setup.py）定义扩展模块并启用 `language_level=3`、`boundscheck=False` 等。

## Rust (PyO3)
- 目标：使用原子与无锁 ring buffer 优化计数与滑窗。
- 结构：
  - crate 名称 `risk_engine_accel`
  - 导出 Py 类 `ShardedLockDict`、`RollingWindowCounter`
- 示例 `Cargo.toml`
```toml
[package]
name = "risk_engine_accel"
version = "0.1.0"
edition = "2021"

[lib]
name = "risk_engine_accel"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.21", features = ["extension-module"] }
```
- 编译：`maturin build --release`，并将产物放入 Python 环境。

> 本项目已通过 `risk_engine.accel` 门面优先加载原生实现，不存在时自动回退到 Python 版本，无需改业务代码。