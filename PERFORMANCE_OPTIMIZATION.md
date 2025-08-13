# 性能优化方案 - 达到百万级吞吐量

## 当前性能基准

- **单线程Python实现**: ~189,000 ops/s
- **平均延迟**: 5.29 微秒
- **瓶颈分析**:
  - Python GIL限制了多核利用
  - 解释器开销
  - 内存分配和垃圾回收

## 优化路径

### 第一阶段：Python层优化（目标：500K ops/s）

1. **使用PyPy解释器**
   ```bash
   # 安装PyPy
   pypy3 -m pip install -r requirements.txt
   pypy3 bench.py
   ```
   预期提升：2-3倍性能

2. **优化热点代码**
   - 使用`__slots__`减少内存开销 ✓ (已实现)
   - 预分配数据结构
   - 减少函数调用开销
   - 使用局部变量缓存

3. **批处理优化**
   ```python
   def on_orders_batch(self, orders: List[Order]):
       """批量处理订单，减少锁竞争"""
       with self._lock:
           for order in orders:
               self._process_order(order)
   ```

### 第二阶段：原生代码加速（目标：2M ops/s）

1. **Cython加速关键模块**

   创建 `risk_engine/accel/sharded_dict.pyx`:
   ```cython
   # cython: language_level=3
   from libc.stdint cimport uint64_t
   from cpython.dict cimport PyDict_GetItem, PyDict_SetItem
   import threading
   
   cdef class FastShardedLockDict:
       cdef:
           list _shards
           list _locks
           int _num_shards
       
       def __cinit__(self, int num_shards=16):
           self._num_shards = num_shards
           self._shards = [dict() for _ in range(num_shards)]
           self._locks = [threading.Lock() for _ in range(num_shards)]
       
       cdef int _get_shard(self, str key):
           return hash(key) % self._num_shards
       
       cpdef void increment(self, str key, double value):
           cdef int shard = self._get_shard(key)
           cdef dict shard_dict = self._shards[shard]
           
           with self._locks[shard]:
               current = shard_dict.get(key, 0.0)
               shard_dict[key] = current + value
   ```

   编译配置 `setup.py`:
   ```python
   from setuptools import setup
   from Cython.Build import cythonize
   
   setup(
       ext_modules=cythonize([
           "risk_engine/accel/sharded_dict.pyx",
           "risk_engine/accel/rolling_window.pyx",
       ], compiler_directives={'language_level': "3"})
   )
   ```

2. **Rust扩展（使用PyO3）**

   创建 `risk_engine_rust/src/lib.rs`:
   ```rust
   use pyo3::prelude::*;
   use std::collections::HashMap;
   use std::sync::{Arc, Mutex};
   
   #[pyclass]
   struct RustShardedDict {
       shards: Vec<Arc<Mutex<HashMap<String, f64>>>>,
   }
   
   #[pymethods]
   impl RustShardedDict {
       #[new]
       fn new(num_shards: usize) -> Self {
           let mut shards = Vec::with_capacity(num_shards);
           for _ in 0..num_shards {
               shards.push(Arc::new(Mutex::new(HashMap::new())));
           }
           RustShardedDict { shards }
       }
       
       fn increment(&self, key: &str, value: f64) {
           let shard_idx = key.bytes().fold(0u64, |acc, b| {
               acc.wrapping_mul(31).wrapping_add(b as u64)
           }) as usize % self.shards.len();
           
           let mut shard = self.shards[shard_idx].lock().unwrap();
           *shard.entry(key.to_string()).or_insert(0.0) += value;
       }
   }
   ```

### 第三阶段：架构优化（目标：10M+ ops/s）

1. **多进程分片架构**

   ```python
   # risk_engine/adapters/sharding.py
   import multiprocessing as mp
   from typing import List, Callable
   
   class ShardedRiskEngine:
       """按账户分片的多进程风控引擎"""
       
       def __init__(self, num_shards: int = mp.cpu_count()):
           self.num_shards = num_shards
           self.processes: List[mp.Process] = []
           self.queues: List[mp.Queue] = []
           
       def shard_key(self, account_id: str) -> int:
           """账户ID到分片的映射"""
           return hash(account_id) % self.num_shards
           
       def route_order(self, order: Order):
           """路由订单到对应分片"""
           shard = self.shard_key(order.account_id)
           self.queues[shard].put(order)
   ```

2. **共享内存优化**

   ```python
   # 使用共享内存避免序列化开销
   import mmap
   import struct
   
   class SharedMemoryBuffer:
       """零拷贝共享内存缓冲区"""
       
       def __init__(self, size: int = 1024 * 1024):
           self.shm = mmap.mmap(-1, size)
           self.offset = 0
           
       def write_order(self, order: Order):
           """直接写入二进制格式"""
           data = struct.pack(
               '!QQ32sId',  # oid, account_id, contract_id, direction, price, volume
               order.oid,
               hash(order.account_id),
               order.contract_id.encode('utf-8'),
               order.direction.value,
               order.price,
               order.volume
           )
           self.shm[self.offset:self.offset+len(data)] = data
           self.offset += len(data)
   ```

3. **DPDK集成（极致性能）**

   ```python
   # 使用DPDK直接从网卡读取数据
   # 需要特殊硬件和内核配置
   from dpdk import DpdkPort, DpdkPacket
   
   class DpdkRiskEngine:
       """基于DPDK的超低延迟风控引擎"""
       
       def __init__(self, port_id: int):
           self.port = DpdkPort(port_id)
           self.port.configure(rx_queues=4, tx_queues=4)
           
       def process_packets(self):
           """直接从网卡处理数据包"""
           while True:
               packets = self.port.rx_burst(max_packets=32)
               for pkt in packets:
                   order = self.parse_order(pkt)
                   self.process_order(order)
   ```

### 第四阶段：硬件加速（目标：100M+ ops/s）

1. **SIMD指令优化**

   ```c
   // 使用AVX2指令集加速批量计算
   #include <immintrin.h>
   
   void batch_increment_volumes(__m256d* volumes, 
                               const __m256d* increments, 
                               size_t count) {
       for (size_t i = 0; i < count; i++) {
           volumes[i] = _mm256_add_pd(volumes[i], increments[i]);
       }
   }
   ```

2. **GPU加速（CUDA）**

   ```cuda
   __global__ void check_volume_limits(
       float* volumes,
       float* thresholds,
       int* violations,
       int n
   ) {
       int idx = blockIdx.x * blockDim.x + threadIdx.x;
       if (idx < n) {
           violations[idx] = volumes[idx] > thresholds[idx] ? 1 : 0;
       }
   }
   ```

3. **FPGA加速**
   - 使用FPGA实现固定规则的硬件加速
   - 适合延迟敏感的简单规则

## 性能测试方案

### 基准测试脚本

```python
# benchmark_suite.py
import time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import numpy as np

def benchmark_single_thread(engine, num_events):
    """单线程基准测试"""
    start = time.perf_counter()
    # ... 处理逻辑
    end = time.perf_counter()
    return num_events / (end - start)

def benchmark_multi_process(engine_factory, num_events, num_processes):
    """多进程基准测试"""
    with ProcessPoolExecutor(max_workers=num_processes) as executor:
        futures = []
        events_per_process = num_events // num_processes
        
        start = time.perf_counter()
        for i in range(num_processes):
            future = executor.submit(process_events, 
                                   engine_factory(), 
                                   events_per_process)
            futures.append(future)
        
        for future in futures:
            future.result()
        
        end = time.perf_counter()
        return num_events / (end - start)
```

### 延迟测试

```python
def measure_latency_percentiles(engine, num_samples=10000):
    """测量延迟百分位数"""
    latencies = []
    
    for i in range(num_samples):
        order = create_test_order(i)
        
        start = time.perf_counter_ns()
        engine.on_order(order)
        end = time.perf_counter_ns()
        
        latencies.append(end - start)
    
    latencies = np.array(latencies)
    return {
        'p50': np.percentile(latencies, 50),
        'p95': np.percentile(latencies, 95),
        'p99': np.percentile(latencies, 99),
        'p999': np.percentile(latencies, 99.9),
    }
```

## 部署建议

1. **硬件配置**
   - CPU: Intel Xeon Gold 6248R 或更高
   - 内存: 128GB+ DDR4 ECC
   - 网卡: Mellanox ConnectX-5 或更高（支持DPDK）
   - 存储: NVMe SSD（用于日志）

2. **系统优化**
   - 关闭CPU频率调节
   - NUMA绑定
   - 大页内存
   - 实时内核补丁

3. **监控指标**
   - 吞吐量（ops/s）
   - 延迟百分位数
   - CPU使用率（每核）
   - 内存带宽使用率
   - 网络包处理延迟

## 总结

通过以上优化方案，可以逐步将系统性能从当前的~19万ops/s提升到：

- **第一阶段**: 50万 ops/s（Python优化）
- **第二阶段**: 200万 ops/s（原生代码）
- **第三阶段**: 1000万+ ops/s（架构优化）
- **第四阶段**: 1亿+ ops/s（硬件加速）

每个阶段的投入产出比不同，建议根据实际业务需求选择合适的优化级别。对于大多数场景，达到第二阶段（200万ops/s）即可满足需求。