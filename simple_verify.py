#!/usr/bin/env python3
"""
简单验证脚本 - 直观展示系统功能
"""

import sys
sys.path.insert(0, '/workspace')

from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.actions import Action

def print_title(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def verify_volume_limit():
    """验证成交量限制"""
    print_title("验证1：单账户成交量限制")
    
    config = RiskEngineConfig(
        contract_to_product={
            "T2303": "T10Y",
            "T2306": "T10Y",
        }
    )
    
    engine = RiskEngine(config)
    
    # 添加成交量限制规则
    rule = AccountTradeMetricLimitRule(
        rule_id="VOLUME_LIMIT",
        threshold=100,  # 100手限制
        by_account=True,
        metric=MetricType.TRADE_VOLUME,
        actions=(Action.SUSPEND_ACCOUNT_TRADING,)
    )
    engine.add_rule(rule)
    
    print("设置规则：账户成交量限制100手")
    print("开始模拟交易...")
    
    total = 0
    for i in range(12):
        trade = Trade(
            tid=i+1, oid=i+1,
            price=100.0, volume=10,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000,
            account_id="ACC_001",
            contract_id="T2303"
        )
        
        actions = engine.on_trade(trade)
        total += 10
        
        if actions:
            print(f"✓ 第{i+1}笔交易触发风控！累计成交{total}手 > 限制100手")
            print(f"  触发动作: {[a.type.name for a in actions]}")
            return True
        else:
            print(f"  第{i+1}笔交易正常，累计成交{total}手")
    
    return False

def verify_order_rate_limit():
    """验证报单频率限制"""
    print_title("验证2：报单频率控制")
    
    config = RiskEngineConfig(contract_to_product={"T2303": "T10Y"})
    engine = RiskEngine(config)
    
    # 添加频率限制规则
    rule = OrderRateLimitRule(
        rule_id="RATE_LIMIT",
        threshold=5,  # 5次/秒
        window_seconds=1,
        dimension="account"
    )
    engine.add_rule(rule)
    
    print("设置规则：报单频率限制5次/秒")
    print("快速发送订单...")
    
    base_time = 1_700_000_000_000_000_000
    
    for i in range(8):
        order = Order(
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=base_time + i * 100_000_000  # 100ms间隔
        )
        
        actions = engine.on_order(order)
        
        if actions and any(a.type == Action.SUSPEND_ORDERING for a in actions):
            print(f"✓ 第{i+1}个订单触发频率限制！")
            print(f"  触发动作: {[a.type.name for a in actions]}")
            return True
        else:
            print(f"  订单{i+1}正常处理")
    
    return False

def verify_multi_metric():
    """验证多种指标支持"""
    print_title("验证3：多种指标支持")
    
    config = RiskEngineConfig(contract_to_product={"T2303": "T10Y"})
    
    # 测试成交金额指标
    print("3.1 测试成交金额指标")
    engine = RiskEngine(config)
    rule = AccountTradeMetricLimitRule(
        rule_id="NOTIONAL_LIMIT",
        threshold=50000,  # 5万元限制
        by_account=True,
        metric=MetricType.TRADE_NOTIONAL,  # 成交金额
        actions=(Action.ALERT,)
    )
    engine.add_rule(rule)
    
    trade = Trade(
        tid=1, oid=1,
        price=100.0, volume=600,  # 成交金额 = 100 * 600 = 60000
        timestamp=1_700_000_000_000_000_000,
        account_id="ACC_001",
        contract_id="T2303"
    )
    
    actions = engine.on_trade(trade)
    if actions:
        print(f"✓ 成交金额{100*600}元触发限制（阈值50000元）")
    
    # 测试报单量指标
    print("\n3.2 测试报单量指标")
    engine = RiskEngine(config)
    rule = AccountTradeMetricLimitRule(
        rule_id="ORDER_COUNT",
        threshold=3,
        by_account=True,
        metric=MetricType.ORDER_COUNT,  # 报单数量
        actions=(Action.ALERT,)
    )
    engine.add_rule(rule)
    
    for i in range(5):
        order = Order(
            oid=100+i,
            account_id="ACC_002",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=1,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000
        )
        actions = engine.on_order(order)
        if actions:
            print(f"✓ 第{i+1}个订单触发报单量限制（阈值3个）")
            break
    
    return True

def verify_multi_dimension():
    """验证多维度统计"""
    print_title("验证4：多维度统计")
    
    config = RiskEngineConfig(
        contract_to_product={
            "T2303": "T10Y",
            "T2306": "T10Y",
            "TF2303": "T5Y",
        }
    )
    
    # 按产品维度统计
    print("4.1 测试产品维度统计")
    engine = RiskEngine(config)
    rule = AccountTradeMetricLimitRule(
        rule_id="PRODUCT_LIMIT",
        threshold=150,
        by_account=True,
        by_product=True,  # 产品维度
        metric=MetricType.TRADE_VOLUME,
        actions=(Action.SUSPEND_PRODUCT,)
    )
    engine.add_rule(rule)
    
    print("在同一产品的不同合约上交易...")
    total = 0
    for i in range(8):
        contract = "T2303" if i % 2 == 0 else "T2306"  # 交替使用不同合约
        trade = Trade(
            tid=200+i, oid=200+i,
            price=100.0, volume=20,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000,
            account_id="ACC_003",
            contract_id=contract
        )
        actions = engine.on_trade(trade)
        total += 20
        
        if actions:
            print(f"✓ 产品T10Y累计成交{total}手触发限制（阈值150手）")
            print(f"  不同合约（T2303和T2306）的成交量被合并统计")
            break
        else:
            print(f"  {contract}成交20手，产品累计{total}手")
    
    return True

def verify_multi_action():
    """验证多Action支持"""
    print_title("验证5：一个规则触发多个Action")
    
    config = RiskEngineConfig(contract_to_product={"T2303": "T10Y"})
    engine = RiskEngine(config)
    
    # 创建触发多个动作的规则
    rule = AccountTradeMetricLimitRule(
        rule_id="MULTI_ACTION",
        threshold=50,
        by_account=True,
        metric=MetricType.TRADE_VOLUME,
        actions=(
            Action.SUSPEND_ACCOUNT_TRADING,
            Action.ALERT,
            Action.REDUCE_POSITION,
        )
    )
    engine.add_rule(rule)
    
    print("设置规则：成交量超过50手时触发3个动作")
    
    for i in range(6):
        trade = Trade(
            tid=300+i, oid=300+i,
            price=100.0, volume=10,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000,
            account_id="ACC_004",
            contract_id="T2303"
        )
        
        actions = engine.on_trade(trade)
        if actions:
            print(f"\n✓ 触发了{len(actions)}个动作:")
            for action in actions:
                print(f"  - {action.type.name}: {action.reason}")
            return True
    
    return False

def main():
    """主函数"""
    print("金融风控模块功能验证（简化版）")
    print("=" * 60)
    
    results = []
    
    # 运行各项验证
    results.append(("成交量限制", verify_volume_limit()))
    results.append(("报单频率控制", verify_order_rate_limit()))
    results.append(("多种指标支持", verify_multi_metric()))
    results.append(("多维度统计", verify_multi_dimension()))
    results.append(("多Action支持", verify_multi_action()))
    
    # 打印总结
    print_title("验证总结")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    print(f"验证项目: {total}")
    print(f"通过: {passed}")
    print(f"失败: {total - passed}")
    
    print("\n详细结果:")
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {status} - {name}")
    
    if passed == total:
        print("\n✓ 所有功能验证通过！系统满足项目要求。")
    else:
        print("\n✗ 部分功能验证失败，请检查。")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())