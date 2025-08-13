# 项目结构说明

## 目录结构

```
risk_engine/
├── __init__.py                 # 包初始化文件
├── README.md                   # 系统文档
├── requirements.txt            # 依赖包列表
├── PROJECT_STRUCTURE.md        # 项目结构说明（本文件）
├── basic_demo.py              # 笔试演示程序
├── bench.py                   # 性能基准测试
│
├── core/                      # 核心模块
│   ├── engine.py              # 主引擎实现
│   ├── models.py              # 数据模型定义
│   ├── actions.py             # Action类型定义
│   ├── metrics.py             # 指标类型定义
│   └── config.py              # 配置管理
│
├── rules/                     # 规则引擎
│   ├── rules.py               # 规则基类和实现
│   └── rule_builder.py        # 规则构建器
│
├── state/                     # 状态管理
│   ├── state.py               # 状态存储和统计
│   └── counters.py            # 计数器实现
│
├── dimensions/                 # 维度管理
│   ├── dimensions.py           # 维度定义和映射
│   └── catalog.py             # 合约目录管理
│
├── stats/                     # 统计功能
│   ├── stats.py               # 统计维度定义
│   └── aggregators.py         # 聚合器实现
│
├── adapters/                  # 适配器
│   ├── input_adapters.py      # 输入数据适配器
│   └── output_adapters.py     # 输出数据适配器
│
├── accel/                     # 加速模块
│   ├── __init__.py            # 加速模块初始化
│   ├── README.md              # 加速实现指南
│   └── cython/                # Cython实现
│   └── rust/                  # Rust实现
│
└── tests/                     # 测试套件
    ├── test_engine.py          # 引擎测试
    ├── test_rules.py           # 规则测试
    ├── test_state.py           # 状态测试
    ├── test_performance.py     # 性能测试
    └── test_integration.py     # 集成测试
```

## 核心模块说明

### 1. 引擎模块 (engine.py)
- **RiskEngine**: 主引擎类，协调所有组件
- **EngineConfig**: 引擎配置类
- 支持高并发处理和低延迟响应

### 2. 数据模型 (models.py)
- **Order**: 订单数据模型
- **Trade**: 成交数据模型
- **Direction**: 买卖方向枚举
- 使用dataclass和slots优化性能

### 3. 规则引擎 (rules.py)
- **Rule**: 规则基类
- **AccountTradeMetricLimitRule**: 账户交易指标限制规则
- **OrderRateLimitRule**: 报单频率控制规则
- 支持自定义规则扩展

### 4. 状态管理 (state.py)
- **MultiDimDailyCounter**: 多维度日统计计数器
- **RollingWindowCounter**: 滑动窗口计数器
- **ShardedLockDict**: 分片锁字典，提高并发性能

### 5. 维度管理 (dimensions.py)
- **InstrumentCatalog**: 合约目录管理
- 支持合约到产品的映射关系
- 支持多维度统计

### 6. 指标系统 (metrics.py)
- **MetricType**: 指标类型枚举
- 支持成交量、成交金额、报单数、撤单数等
- 可扩展新的指标类型

### 7. Action系统 (actions.py)
- **Action**: 风控处置动作枚举
- **EmittedAction**: 触发的Action记录
- 支持多种处置指令

## 设计原则

### 1. 高性能
- 分片锁设计，减少锁竞争
- 无阻塞读，最大化并发性能
- 轻量对象，优化内存使用
- 常量时间路径，保证性能稳定

### 2. 高扩展性
- 插件式规则系统
- 多维度统计支持
- 动态配置更新
- 自定义指标扩展

### 3. 易用性
- 简洁的API设计
- 丰富的配置选项
- 完善的文档和示例
- 直观的错误处理

### 4. 生产就绪
- 完善的测试覆盖
- 性能基准测试
- 监控和统计功能
- 错误处理和恢复

## 扩展开发指南

### 1. 添加新规则
```python
from risk_engine.rules import Rule, RuleContext, RuleResult

class CustomRule(Rule):
    def __init__(self, rule_id: str, custom_param: str):
        self.rule_id = rule_id
        self.custom_param = custom_param
    
    def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
        # 实现自定义规则逻辑
        pass
    
    def on_trade(self, ctx: RuleContext, trade: Trade) -> Optional[RuleResult]:
        # 实现成交相关的规则逻辑
        pass
```

### 2. 添加新指标
```python
from risk_engine.metrics import MetricType

class CustomMetricType(MetricType):
    PROFIT_LOSS = "profit_loss"
    POSITION = "position"
```

### 3. 添加新Action
```python
from risk_engine.actions import Action

class CustomAction(Action):
    CUSTOM_ACTION = auto()
```

## 性能优化

### 1. 内存优化
- 使用slots减少内存占用
- 自动清理过期数据
- 预分配数据结构

### 2. 并发优化
- 分片锁减少竞争
- 无阻塞读操作
- 轻量级对象创建

### 3. 算法优化
- 常量时间路径
- 滑动窗口算法
- 高效的数据结构

## 测试策略

### 1. 单元测试
- 每个模块都有对应的测试文件
- 使用pytest框架
- 高测试覆盖率

### 2. 性能测试
- 基准测试脚本
- 压力测试
- 内存使用监控

### 3. 集成测试
- 端到端测试
- 规则组合测试
- 异常情况测试

## 部署说明

### 1. 开发环境
```bash
pip install -r requirements.txt
python -m pytest tests/
python3 basic_demo.py
```

### 2. 生产环境
- 根据CPU核心数调整配置
- 监控内存使用情况
- 设置告警阈值

### 3. 性能调优
- 调整工作线程数
- 优化规则执行顺序
- 监控系统指标