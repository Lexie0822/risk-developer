"""
金融风控系统演示脚本
"""
import time
from datetime import datetime

from src.models import Order, Trade, Direction, ActionType
from src.config import create_default_config, VolumeControlConfig, FrequencyControlConfig
from src.config import MetricType, AggregationLevel, ProductConfig
from src.engine import RiskControlEngine


def print_section(title):
    """打印分节标题"""
    print(f"\n{'='*60}")
    print(f"{title:^60}")
    print('='*60)


def demo_basic_volume_control():
    """演示基本的成交量控制"""
    print_section("演示1: 单账户日成交量限制")
    
    # 创建风控引擎
    config = create_default_config()
    engine = RiskControlEngine(config)
    
    account_id = "ACC_001"
    contract_id = "T2303"
    
    print(f"\n配置: 单账户日成交量限制 1000 手")
    print(f"测试账户: {account_id}")
    print(f"测试合约: {contract_id}")
    
    # 模拟交易
    base_timestamp = int(datetime.now().timestamp() * 1_000_000_000)
    total_volume = 0
    
    for i in range(102):  # 生成1020手的成交
        order = Order(
            oid=i,
            account_id=account_id,
            contract_id=contract_id,
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=base_timestamp + i * 1000000
        )
        
        trade = Trade(
            tid=1000+i,
            oid=i,
            price=100.0,
            volume=10,
            timestamp=base_timestamp + i * 1000000 + 500000
        )
        
        # 处理订单和成交
        order_actions = engine.process_order(order)
        trade_actions = engine.process_trade(trade)
        
        total_volume += 10
        
        # 检查是否触发风控
        if trade_actions:
            print(f"\n⚠️  成交 {i+1} 触发风控!")
            for action in trade_actions:
                print(f"   动作: {action.action_type.value}")
                print(f"   原因: {action.reason}")
                print(f"   当前成交量: {total_volume} 手")
            break
    
    # 显示统计信息
    stats = engine.get_statistics(account_id)
    print(f"\n📊 账户统计信息:")
    print(f"   日成交量: {stats['trade_volume']['account']['daily']['value']} 手")
    print(f"   日成交笔数: {stats['trade_volume']['account']['daily']['count']} 笔")


def demo_frequency_control():
    """演示报单频率控制"""
    print_section("演示2: 报单频率控制")
    
    config = create_default_config()
    engine = RiskControlEngine(config)
    
    account_id = "ACC_002"
    contract_id = "T2306"
    
    print(f"\n配置: 报单频率限制 50次/秒")
    print(f"测试账户: {account_id}")
    print(f"测试合约: {contract_id}")
    
    base_timestamp = int(datetime.now().timestamp() * 1_000_000_000)
    
    # 快速发送订单
    print("\n📤 快速发送订单...")
    for i in range(55):
        order = Order(
            oid=200+i,
            account_id=account_id,
            contract_id=contract_id,
            direction=Direction.ASK if i % 2 else Direction.BID,
            price=100.0 + i * 0.1,
            volume=1,
            timestamp=base_timestamp + i * 10_000_000  # 每10毫秒一个订单
        )
        
        actions = engine.process_order(order)
        
        if actions:
            print(f"\n⚠️  订单 {200+i} 触发风控!")
            for action in actions:
                print(f"   动作: {action.action_type.value}")
                print(f"   原因: {action.reason}")
            
            # 尝试发送下一个订单（应该被拦截）
            next_order = Order(
                oid=300,
                account_id=account_id,
                contract_id=contract_id,
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=base_timestamp + 600_000_000
            )
            next_actions = engine.process_order(next_order)
            if next_actions:
                print(f"\n🚫 后续订单被拦截:")
                for action in next_actions:
                    print(f"   动作: {action.action_type.value}")
                    print(f"   原因: {action.reason}")
            break
    
    # 显示暂停的目标
    suspended = engine.get_suspended_targets()
    if suspended:
        print(f"\n📋 当前暂停的目标:")
        for rule_name, targets in suspended.items():
            print(f"   {rule_name}: {targets}")


def demo_multi_dimension_stats():
    """演示多维度统计"""
    print_section("演示3: 多维度统计和产品级别控制")
    
    config = create_default_config()
    
    # 添加产品维度的成交金额控制
    product_amount_rule = VolumeControlConfig(
        rule_name="product_amount_limit",
        description="产品维度成交金额限制",
        metric_type=MetricType.TRADE_AMOUNT,
        threshold=10_000_000,  # 1000万
        aggregation_level=AggregationLevel.PRODUCT,
        actions=["warning"],
        priority=15
    )
    config.add_rule(product_amount_rule)
    
    engine = RiskControlEngine(config)
    
    print("\n配置:")
    print("  - 账户维度: 日成交量限制 1000 手")
    print("  - 产品维度: 日成交金额限制 1000 万")
    
    # 模拟多个账户在同一产品的不同合约上交易
    accounts = ["ACC_101", "ACC_102", "ACC_103"]
    contracts = ["T2303", "T2306", "T2309"]  # 同属于10年期国债期货产品
    
    base_timestamp = int(datetime.now().timestamp() * 1_000_000_000)
    order_id = 1000
    trade_id = 10000
    
    print("\n📈 模拟交易...")
    total_amount = 0
    
    for round in range(5):
        for account in accounts:
            for contract in contracts:
                order = Order(
                    oid=order_id,
                    account_id=account,
                    contract_id=contract,
                    direction=Direction.BID if order_id % 2 else Direction.ASK,
                    price=95.0 + round,  # 价格逐渐上涨
                    volume=100,  # 每笔100手
                    timestamp=base_timestamp + order_id * 1000000
                )
                
                trade = Trade(
                    tid=trade_id,
                    oid=order_id,
                    price=order.price,
                    volume=order.volume,
                    timestamp=order.timestamp + 500000
                )
                
                engine.process_order(order)
                actions = engine.process_trade(trade)
                
                total_amount += trade.price * trade.volume * 10000  # 假设每手面值1万
                
                if actions:
                    print(f"\n⚠️  触发风控!")
                    print(f"   账户: {account}, 合约: {contract}")
                    print(f"   产品总成交金额: {total_amount:,.0f}")
                    for action in actions:
                        print(f"   动作: {action.action_type.value}")
                        print(f"   原因: {action.reason}")
                
                order_id += 1
                trade_id += 1
    
    # 显示各维度统计
    print("\n📊 统计汇总:")
    
    # 账户维度
    print("\n账户维度成交量:")
    for account in accounts:
        stats = engine.get_statistics(account)
        volume = stats.get('trade_volume', {}).get('account', {}).get('daily', {}).get('value', 0)
        print(f"  {account}: {volume} 手")
    
    # 产品维度
    print("\n产品维度统计:")
    product_stats = engine.get_statistics("T_FUTURES")
    if 'trade_amount' in product_stats and 'product' in product_stats['trade_amount']:
        amount = product_stats['trade_amount']['product']['daily']['value']
        print(f"  10年期国债期货: {amount:,.0f} 元")


def demo_dynamic_configuration():
    """演示动态配置更新"""
    print_section("演示4: 动态配置更新")
    
    config = create_default_config()
    engine = RiskControlEngine(config)
    
    print("\n初始配置:")
    for rule_name, rule in config.rules.items():
        print(f"  - {rule_name}: {rule.description}")
    
    # 添加新产品
    print("\n➕ 添加新产品: 5年期国债期货")
    tf_futures = ProductConfig(
        product_id="TF_FUTURES",
        product_name="5年期国债期货",
        contracts=["TF2303", "TF2306", "TF2309"],
        exchange="CFFEX"
    )
    engine.add_product(tf_futures)
    
    # 添加新规则
    print("\n➕ 添加新规则: 合约维度报单量限制")
    contract_order_rule = VolumeControlConfig(
        rule_name="contract_order_limit",
        description="合约维度日报单量限制",
        metric_type=MetricType.ORDER_COUNT,
        threshold=10000,  # 10000笔
        aggregation_level=AggregationLevel.CONTRACT,
        actions=["warning"],
        priority=8
    )
    config.add_rule(contract_order_rule)
    
    # 重新加载配置
    engine.reload_config(config)
    
    print("\n更新后的配置:")
    for rule_name, rule in config.rules.items():
        print(f"  - {rule_name}: {rule.description}")
    
    print("\n产品列表:")
    for product_id, product in config.products.items():
        print(f"  - {product_id}: {product.product_name} ({len(product.contracts)} 个合约)")


def main():
    """主函数"""
    print("\n" + "🏦 金融风控系统演示 🏦".center(60))
    print("="*60)
    
    demos = [
        ("1", "单账户日成交量限制", demo_basic_volume_control),
        ("2", "报单频率控制", demo_frequency_control),
        ("3", "多维度统计和产品控制", demo_multi_dimension_stats),
        ("4", "动态配置更新", demo_dynamic_configuration),
        ("5", "运行所有演示", None)
    ]
    
    while True:
        print("\n请选择演示项目:")
        for num, desc, _ in demos:
            print(f"  {num}. {desc}")
        print("  0. 退出")
        
        choice = input("\n请输入选项 (0-5): ").strip()
        
        if choice == "0":
            print("\n感谢使用! 👋")
            break
        elif choice == "5":
            # 运行所有演示
            for num, desc, func in demos[:-1]:
                if func:
                    func()
                    input("\n按回车继续...")
        else:
            # 运行选定的演示
            for num, desc, func in demos:
                if num == choice and func:
                    func()
                    input("\n按回车继续...")
                    break
            else:
                print("\n❌ 无效的选项，请重试")


if __name__ == "__main__":
    main()