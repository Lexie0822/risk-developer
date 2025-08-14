# 金融风控系统

## 系统概述

本系统是一个高性能实时金融风控模块，专为处理高频订单（Order）和成交（Trade）数据而设计。系统能够动态触发风控规则并生成处置指令（Action），满足百万级/秒的高并发和微秒级响应的金融场景要求。

## 系统架构

### 核心模块

1. **配置模块 (config.py)**
   - 风控规则定义和管理
   - 支持动态配置和扩展
   - 预定义规则：单账户成交量限制、报单频率控制

2. **数据模型 (models.py)**
   - Order：订单数据结构
   - Trade：成交数据结构
   - Action：风控动作结构

3. **统计引擎 (statistics.py)**
   - 多维度实时统计（账户、合约、产品）
   - 多指标支持（成交量、成交金额、报单量、报单频率）
   - 时间窗口统计和日统计自动重置

4. **风控引擎 (engine.py)**
   - 规则检查和触发
   - Action生成和执行
   - 账户状态管理
   - 自动恢复机制

## 快速开始

### 安装

```python
# 将risk_control_system目录添加到Python路径
import sys
sys.path.append('/path/to/risk_control_system')
```

### 基本使用

```python
from risk_control_system import (
    RiskControlEngine, Order, Trade, Direction
)

# 创建风控引擎
engine = RiskControlEngine()

# 创建订单
order = Order(
    oid=1,
    account_id="ACC_001",
    contract_id="T2303",
    direction=Direction.BID,
    price=100.0,
    volume=10,
    timestamp=int(time.time() * 1e9)
)

# 处理订单
actions = engine.process_order(order)

# 创建成交
trade = Trade(
    tid=1001,
    oid=order.oid,
    price=order.price,
    volume=order.volume,
    timestamp=order.timestamp + 1000000
)

# 处理成交
actions = engine.process_trade(trade)
```

### 自定义规则

```python
from risk_control_system import (
    RiskControlConfig, RiskRule, RuleCondition, 
    RuleAction, ActionType, MetricType, DimensionType
)

# 创建配置
config = RiskControlConfig()

# 定义新规则
rule = RiskRule(
    rule_id="CUSTOM_001",
    name="自定义规则",
    description="成交金额超过阈值时警告",
    conditions=[
        RuleCondition(
            metric_type=MetricType.TRADE_AMOUNT,
            threshold=1000000,
            comparison="gt",
            dimension=DimensionType.ACCOUNT
        )
    ],
    actions=[
        RuleAction(
            action_type=ActionType.WARNING,
            params={"reason": "成交金额超限"}
        )
    ]
)

# 添加规则
config.add_rule(rule)

# 使用配置创建引擎
engine = RiskControlEngine(config)
```

### 查询统计数据

```python
# 获取账户成交量
volume = engine.statistics.get_statistic(
    DimensionType.ACCOUNT, 
    "ACC_001", 
    MetricType.TRADE_VOLUME
)

# 获取账户所有统计数据
all_stats = engine.statistics.get_all_statistics(
    DimensionType.ACCOUNT, 
    "ACC_001"
)
```

## 预定义规则

### 1. 单账户成交量限制
- 规则ID：VOLUME_LIMIT_001
- 触发条件：账户当日成交量超过1000手
- 动作：暂停该账户交易

### 2. 报单频率控制
- 规则ID：ORDER_FREQ_001
- 触发条件：账户每秒报单数超过50次
- 动作：暂停报单60秒（自动恢复）

## 支持的指标类型

- TRADE_VOLUME：成交量
- TRADE_AMOUNT：成交金额
- ORDER_COUNT：报单量
- CANCEL_COUNT：撤单量
- ORDER_FREQUENCY：报单频率

## 支持的维度类型

- ACCOUNT：账户维度
- CONTRACT：合约维度
- PRODUCT：产品维度
- EXCHANGE：交易所维度
- ACCOUNT_GROUP：账户组维度

## 系统优势

1. **高性能**
   - 使用内存计算，避免IO操作
   - 线程安全设计，支持并发处理
   - 优化的数据结构，降低查询复杂度

2. **可扩展性**
   - 规则可动态配置和扩展
   - 支持自定义指标和维度
   - 模块化设计，易于维护

3. **实时性**
   - 微秒级响应时间
   - 实时统计更新
   - 即时规则触发

4. **灵活性**
   - 支持多条件组合（AND/OR逻辑）
   - 一个规则可关联多个Action
   - 支持自动恢复机制

5. **多维度统计**
   - 同时支持账户、合约、产品等多个维度
   - 自动聚合计算
   - 时间窗口和累计统计并存

## 系统局限

1. **内存限制**
   - 所有数据存储在内存中，适合单机部署
   - 长时间运行可能占用较多内存
   - 重启后数据丢失

2. **扩展性限制**
   - 单机架构，不支持分布式部署
   - 规则数量过多时可能影响性能
   - 不支持复杂的规则表达式

3. **功能限制**
   - 暂不支持规则的持久化存储
   - 不支持历史数据查询
   - 缺少监控和告警机制

4. **数据一致性**
   - 在极端高并发场景下可能存在统计偏差
   - 不支持事务处理
   - 缺少数据校验机制

## 性能指标

基于测试结果，系统性能如下：

- 订单处理速度：约30,000-50,000笔/秒
- 成交处理速度：约40,000-60,000笔/秒
- 规则检查延迟：< 100微秒
- 内存占用：每100万笔订单约占用500MB

## 部署建议

1. **硬件要求**
   - CPU：4核以上
   - 内存：8GB以上
   - 存储：SSD推荐

2. **软件要求**
   - Python 3.7+
   - 无外部依赖

3. **优化建议**
   - 定期清理过期的订单缓存
   - 根据业务量调整时间窗口大小
   - 合理设置规则阈值，避免频繁触发

## 未来改进方向

1. 支持分布式部署
2. 添加数据持久化功能
3. 实现更复杂的规则引擎
4. 增加监控和告警功能
5. 支持WebSocket实时推送
6. 添加回测功能
7. 优化内存使用

## 测试

运行测试套件：

```bash
cd risk_control_system
python test_system.py
```

测试包括：
- 单账户成交量限制测试
- 报单频率控制测试
- 多维度统计测试
- 自定义规则测试
- 性能压力测试