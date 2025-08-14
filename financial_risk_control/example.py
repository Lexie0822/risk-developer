#!/usr/bin/env python3
"""
金融风控系统快速示例
展示系统的基本使用方法
"""

from datetime import datetime
from src.models import Order, Trade, Direction
from src.config import create_default_config
from src.engine import RiskControlEngine


def main():
    print("=== 金融风控系统快速示例 ===\n")
    
    # 1. 创建风控引擎
    config = create_default_config()
    engine = RiskControlEngine(config)
    
    # 2. 模拟交易场景
    account_id = "ACC_TEST"
    contract_id = "T2303"
    base_timestamp = int(datetime.now().timestamp() * 1_000_000_000)
    
    print(f"账户: {account_id}")
    print(f"合约: {contract_id}")
    print(f"规则: 日成交量限制1000手，报单频率限制50次/秒\n")
    
    # 3. 正常交易
    print("1. 正常交易测试:")
    for i in range(5):
        order = Order(
            oid=i,
            account_id=account_id,
            contract_id=contract_id,
            direction=Direction.BID,
            price=100.0,
            volume=100,
            timestamp=base_timestamp + i * 1_000_000_000  # 每秒1单
        )
        
        actions = engine.process_order(order)
        print(f"   订单{i}: {'正常' if not actions else '触发风控'}")
        
        # 模拟成交
        trade = Trade(
            tid=1000+i,
            oid=i,
            price=100.0,
            volume=100,
            timestamp=order.timestamp + 100_000_000
        )
        
        actions = engine.process_trade(trade)
        if actions:
            print(f"   成交{i}: 触发风控 - {actions[0].reason}")
    
    # 4. 查看统计信息
    stats = engine.get_statistics(account_id)
    print(f"\n2. 当前统计:")
    print(f"   日成交量: {stats['trade_volume']['account']['daily']['value']} 手")
    print(f"   日成交笔数: {stats['trade_volume']['account']['daily']['count']} 笔")
    
    # 5. 频率控制测试
    print("\n3. 频率控制测试:")
    print("   快速发送60个订单...")
    
    trigger_count = 0
    for i in range(60):
        order = Order(
            oid=100+i,
            account_id=f"{account_id}_FREQ",
            contract_id=contract_id,
            direction=Direction.ASK,
            price=99.0,
            volume=1,
            timestamp=base_timestamp + 10_000_000_000 + i * 10_000_000  # 10ms间隔
        )
        
        actions = engine.process_order(order)
        if actions and trigger_count == 0:
            trigger_count = i + 1
            print(f"   在第{trigger_count}个订单触发频率限制")
            print(f"   原因: {actions[0].reason}")
            break
    
    # 6. 查看暂停的目标
    suspended = engine.get_suspended_targets()
    if suspended:
        print("\n4. 当前暂停的目标:")
        for rule, targets in suspended.items():
            print(f"   {rule}: {targets}")
    
    print("\n示例完成！")


if __name__ == "__main__":
    main()