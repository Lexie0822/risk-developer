#!/usr/bin/env python3
"""
撤单功能演示脚本
展示撤单量限制规则的使用
"""

import time
from risk_engine import (
    RiskEngine, EngineConfig, Order, Trade, Cancel, Direction, Action,
    AccountTradeMetricLimitRule, MetricType
)

def main():
    print("=== 撤单功能演示 ===\n")
    
    # 创建风控引擎，配置撤单量限制规则
    engine = RiskEngine(
        EngineConfig(
            contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
            contract_to_exchange={"T2303": "CFFEX", "T2306": "CFFEX"},
        ),
        rules=[
            AccountTradeMetricLimitRule(
                rule_id="CANCEL-LIMIT-5",
                metric=MetricType.CANCEL_COUNT,
                threshold=5,  # 每日最多5次撤单
                actions=(Action.SUSPEND_ORDERING,),  # 超过阈值暂停报单
                by_account=True,
                by_product=True,
            ),
        ],
    )
    
    # 基础时间戳
    base_ts = int(time.time() * 1e9)
    
    print("1. 提交订单...")
    orders = []
    for i in range(1, 7):  # 提交6个订单
        order = Order(
            oid=i,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=base_ts + i * 1000000  # 间隔1ms
        )
        orders.append(order)
        actions = engine.ingest_order(order)
        print(f"   订单{i}: 无风控动作" if not actions else f"   订单{i}: {[a.type.name for a in actions]}")
    
    print("\n2. 开始撤单...")
    for i in range(1, 7):  # 撤销6个订单（超过阈值5）
        cancel = Cancel(
            cancel_id=i + 100,
            oid=i,  # 撤销对应的订单
            volume=10,
            timestamp=base_ts + (i + 10) * 1000000,
            account_id="ACC_001",  # 可以不填，会从订单自动补全
            contract_id="T2303"
        )
        actions = engine.ingest_cancel(cancel)
        if actions:
            print(f"   撤单{i}: 触发风控 -> {[a.type.name for a in actions]}")
        else:
            print(f"   撤单{i}: 无风控动作")
    
    print("\n3. 验证不同产品维度...")
    # 在另一个产品上测试（应该是独立计数）
    order_t2306 = Order(
        oid=10,
        account_id="ACC_001", 
        contract_id="T2306",  # 不同合约但同产品T10Y
        direction=Direction.BID,
        price=101.0,
        volume=10,
        timestamp=base_ts + 20 * 1000000
    )
    engine.ingest_order(order_t2306)
    
    cancel_t2306 = Cancel(
        cancel_id=110,
        oid=10,
        volume=10, 
        timestamp=base_ts + 21 * 1000000,
        account_id="ACC_001",
        contract_id="T2306"
    )
    actions = engine.ingest_cancel(cancel_t2306)
    print(f"   T2306撤单: {'无风控动作' if not actions else [a.type.name for a in actions]} (产品维度已超限)")
    
    print("\n=== 演示完成 ===")

if __name__ == "__main__":
    main()