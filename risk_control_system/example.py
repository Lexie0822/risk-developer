"""
金融风控系统使用示例
展示系统的基本功能和用法
"""
import time
import random

from risk_control_system.models import Order, Trade, Direction
from risk_control_system.config import (
    RiskControlConfig, RiskRule, RuleCondition, 
    RuleAction, ActionType, MetricType, DimensionType
)
from risk_control_system.engine import RiskControlEngine


def example_basic_usage():
    """基本使用示例"""
    print("=== 基本使用示例 ===")
    
    # 创建风控引擎（使用默认配置）
    engine = RiskControlEngine()
    
    # 创建订单
    order = Order(
        oid=1,
        account_id="ACC_001",
        contract_id="T2303",
        direction=Direction.BID,
        price=100.5,
        volume=20,
        timestamp=int(time.time() * 1e9)
    )
    
    print(f"创建订单: {order.oid}, 账户: {order.account_id}, "
          f"合约: {order.contract_id}, 数量: {order.volume}手")
    
    # 处理订单
    actions = engine.process_order(order)
    print(f"订单处理完成，触发动作数: {len(actions)}")
    
    # 创建成交
    trade = Trade(
        tid=1001,
        oid=order.oid,
        price=order.price,
        volume=order.volume,
        timestamp=order.timestamp + 1_000_000  # 1毫秒后成交
    )
    
    print(f"创建成交: {trade.tid}, 价格: {trade.price}, "
          f"数量: {trade.volume}手")
    
    # 处理成交
    actions = engine.process_trade(trade)
    print(f"成交处理完成，触发动作数: {len(actions)}")
    
    # 查询统计
    volume = engine.statistics.get_statistic(
        DimensionType.ACCOUNT, 
        "ACC_001", 
        MetricType.TRADE_VOLUME
    )
    print(f"账户ACC_001当前成交量: {volume}手")


def example_trigger_volume_limit():
    """触发成交量限制示例"""
    print("\n=== 触发成交量限制示例 ===")
    
    engine = RiskControlEngine()
    account_id = "ACC_002"
    
    print(f"模拟账户{account_id}大量成交...")
    
    # 循环生成订单和成交，直到触发限制
    for i in range(110):  # 每笔10手，110笔 = 1100手 > 1000手限制
        order = Order(
            oid=i + 1000,
            account_id=account_id,
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=int(time.time() * 1e9) + i * 1_000_000_000
        )
        
        # 处理订单
        order_actions = engine.process_order(order)
        
        # 如果订单被拒绝，说明账户已被暂停
        if any(a.action_type == "REJECT_ORDER" for a in order_actions):
            print(f"订单{order.oid}被拒绝: 账户已被暂停交易")
            break
        
        # 创建成交
        trade = Trade(
            tid=i + 2000,
            oid=order.oid,
            price=order.price,
            volume=order.volume,
            timestamp=order.timestamp + 1_000_000
        )
        
        # 处理成交
        trade_actions = engine.process_trade(trade)
        
        if trade_actions:
            print(f"第{i+1}笔成交后触发风控:")
            for action in trade_actions:
                print(f"  - {action.action_type}: {action.reason}")
            
            # 检查账户状态
            if engine.is_account_suspended(account_id):
                print(f"账户{account_id}已被暂停交易")
                break
    
    # 显示最终统计
    volume = engine.statistics.get_statistic(
        DimensionType.ACCOUNT, account_id, MetricType.TRADE_VOLUME
    )
    print(f"账户{account_id}最终成交量: {volume}手")


def example_order_frequency_control():
    """报单频率控制示例"""
    print("\n=== 报单频率控制示例 ===")
    
    engine = RiskControlEngine()
    account_id = "ACC_003"
    
    print(f"模拟账户{account_id}高频报单...")
    
    base_timestamp = int(time.time() * 1e9)
    orders_sent = 0
    
    # 在0.8秒内发送55个订单，超过50个/秒的限制
    for i in range(55):
        order = Order(
            oid=i + 3000,
            account_id=account_id,
            contract_id="TF2303",
            direction=Direction.ASK,
            price=95.0,
            volume=1,
            timestamp=base_timestamp + i * 15_000_000  # 每15毫秒一个订单
        )
        
        actions = engine.process_order(order)
        
        if actions:
            print(f"第{i+1}个订单触发风控:")
            for action in actions:
                print(f"  - {action.action_type}: {action.reason}")
            
            if engine.is_order_suspended(account_id):
                print(f"账户{account_id}报单已被暂停")
                break
        else:
            orders_sent += 1
    
    # 显示统计
    order_freq = engine.statistics.get_statistic(
        DimensionType.ACCOUNT, account_id, MetricType.ORDER_FREQUENCY,
        base_timestamp + 1_000_000_000
    )
    print(f"成功发送订单数: {orders_sent}")
    print(f"当前报单频率: {order_freq}个/秒")


def example_custom_rule():
    """自定义规则示例"""
    print("\n=== 自定义规则示例 ===")
    
    # 创建自定义配置
    config = RiskControlConfig()
    
    # 定义一个成交金额限制规则
    amount_rule = RiskRule(
        rule_id="CUSTOM_AMOUNT_001",
        name="大额成交警告",
        description="单笔成交金额超过50万时发出警告",
        conditions=[
            RuleCondition(
                metric_type=MetricType.TRADE_AMOUNT,
                threshold=500000,
                comparison="gt",
                dimension=DimensionType.CONTRACT
            )
        ],
        actions=[
            RuleAction(
                action_type=ActionType.WARNING,
                params={"reason": "大额成交", "level": "high"}
            )
        ]
    )
    
    config.add_rule(amount_rule)
    
    # 创建引擎
    engine = RiskControlEngine(config)
    
    # 生成大额订单
    order = Order(
        oid=9999,
        account_id="ACC_VIP",
        contract_id="TS2303",
        direction=Direction.BID,
        price=10000.0,  # 高价格
        volume=100,     # 大数量
        timestamp=int(time.time() * 1e9)
    )
    
    print(f"创建大额订单: 价格={order.price}, 数量={order.volume}, "
          f"金额={order.price * order.volume}")
    
    # 处理订单和成交
    engine.process_order(order)
    
    trade = Trade(
        tid=19999,
        oid=order.oid,
        price=order.price,
        volume=order.volume,
        timestamp=order.timestamp + 1_000_000
    )
    
    actions = engine.process_trade(trade)
    
    if actions:
        print("触发自定义规则:")
        for action in actions:
            print(f"  - {action.action_type}: {action.reason}")
            print(f"    参数: {action.params}")


def example_multi_dimension_stats():
    """多维度统计示例"""
    print("\n=== 多维度统计示例 ===")
    
    engine = RiskControlEngine()
    
    # 模拟数据
    test_data = [
        ("ACC_001", "T2303", 30, 100.0),
        ("ACC_001", "T2306", 20, 100.5),
        ("ACC_001", "TF2303", 25, 95.0),
        ("ACC_002", "T2303", 40, 100.0),
        ("ACC_002", "T2306", 35, 100.5),
        ("ACC_003", "TF2303", 50, 95.0),
        ("ACC_003", "TF2306", 45, 95.5),
    ]
    
    print("生成测试交易数据...")
    
    oid = 10000
    tid = 20000
    
    for account_id, contract_id, volume, price in test_data:
        order = Order(
            oid=oid,
            account_id=account_id,
            contract_id=contract_id,
            direction=Direction.BID,
            price=price,
            volume=volume,
            timestamp=int(time.time() * 1e9)
        )
        
        trade = Trade(
            tid=tid,
            oid=order.oid,
            price=order.price,
            volume=order.volume,
            timestamp=order.timestamp + 1_000_000
        )
        
        engine.process_order(order)
        engine.process_trade(trade)
        
        oid += 1
        tid += 1
    
    # 显示多维度统计结果
    print("\n账户维度统计:")
    for account in ["ACC_001", "ACC_002", "ACC_003"]:
        stats = engine.statistics.get_all_statistics(
            DimensionType.ACCOUNT, account
        )
        volume = stats.get(MetricType.TRADE_VOLUME, 0)
        amount = stats.get(MetricType.TRADE_AMOUNT, 0)
        print(f"  {account}: 成交量={volume}手, 成交金额={amount:,.2f}")
    
    print("\n合约维度统计:")
    for contract in ["T2303", "T2306", "TF2303", "TF2306"]:
        volume = engine.statistics.get_statistic(
            DimensionType.CONTRACT, contract, MetricType.TRADE_VOLUME
        )
        if volume > 0:
            print(f"  {contract}: {volume}手")
    
    print("\n产品维度统计:")
    for product in ["T", "TF"]:
        volume = engine.statistics.get_statistic(
            DimensionType.PRODUCT, product, MetricType.TRADE_VOLUME
        )
        print(f"  {product}系列: {volume}手")


def main():
    """运行所有示例"""
    print("金融风控系统使用示例")
    print("=" * 50)
    
    # 运行各个示例
    example_basic_usage()
    example_trigger_volume_limit()
    example_order_frequency_control()
    example_custom_rule()
    example_multi_dimension_stats()
    
    print("\n" + "=" * 50)
    print("示例运行完成")


if __name__ == "__main__":
    main()