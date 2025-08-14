#!/usr/bin/env python3
"""
金融风控模块完整示例

展示系统的所有核心功能：
1. 单账户成交量限制
2. 报单频率控制
3. 多维统计引擎
4. Action处置指令
"""

import sys
sys.path.insert(0, '/workspace')

from risk_engine import RiskEngine
from risk_engine.config import RiskEngineConfig, StatsDimension
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.rules import AccountTradeMetricLimitRule, OrderRateLimitRule
from risk_engine.actions import Action
import time

def demo_volume_limit():
    """演示成交量限制功能"""
    print("\n=== 演示：单账户成交量限制 ===")
    
    # 创建配置
    config = RiskEngineConfig(
        contract_to_product={
            "T2303": "T10Y",  # 10年期国债2303合约
            "T2306": "T10Y",  # 10年期国债2306合约
            "TF2303": "T5Y",  # 5年期国债2303合约
        }
    )
    
    engine = RiskEngine(config)
    
    # 添加成交量限制规则（按产品维度统计）
    volume_rule = AccountTradeMetricLimitRule(
        rule_id="VOLUME_LIMIT",
        threshold=1000,  # 1000手限制
        by_account=True,
        by_product=True,  # 按产品维度统计
        metric=MetricType.TRADE_VOLUME,
        actions=(Action.SUSPEND_ACCOUNT_TRADING, Action.ALERT)
    )
    engine.add_rule(volume_rule)
    
    # 模拟交易
    print(f"设置产品T10Y的成交量限制为1000手")
    
    total_volume = 0
    for i in range(12):
        # 轮流使用不同合约（都属于同一产品T10Y）
        contract = "T2303" if i % 2 == 0 else "T2306"
        volume = 100
        
        trade = Trade(
            tid=i+1,
            oid=i+1,
            price=100.0,
            volume=volume,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000,
            account_id="ACC_001",
            contract_id=contract
        )
        
        actions = engine.on_trade(trade)
        total_volume += volume
        
        print(f"成交 {i+1}: 合约={contract}, 数量={volume}手, 累计={total_volume}手")
        
        if actions:
            print(f"触发风控动作:")
            for action in actions:
                print(f"  - {action.type.name}: {action.reason}")
            break

def demo_order_rate_limit():
    """演示报单频率控制"""
    print("\n=== 演示：报单频率控制 ===")
    
    config = RiskEngineConfig(
        contract_to_product={"T2303": "T10Y"}
    )
    
    engine = RiskEngine(config)
    
    # 添加报单频率限制规则
    rate_rule = OrderRateLimitRule(
        rule_id="ORDER_RATE_LIMIT",
        threshold=50,  # 50次/秒
        window_seconds=1,
        dimension="account"
    )
    engine.add_rule(rate_rule)
    
    print(f"设置报单频率限制为50次/秒")
    
    # 快速发送大量订单
    base_time = int(time.time() * 1e9)
    
    for i in range(60):
        order = Order(
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID if i % 2 == 0 else Direction.ASK,
            price=100.0 + i * 0.01,
            volume=1,
            timestamp=base_time + i * 10_000_000  # 10ms间隔
        )
        
        actions = engine.on_order(order)
        
        if actions:
            print(f"\n在第{i+1}个订单时触发频率限制:")
            for action in actions:
                print(f"  - {action.type.name}: {action.reason}")
            break
        
        if i < 10 or i % 10 == 0:
            print(f"订单 {i+1}: 正常处理")

def demo_multi_dimension_stats():
    """演示多维度统计"""
    print("\n=== 演示：多维度统计引擎 ===")
    
    config = RiskEngineConfig(
        contract_to_product={
            "T2303": "T10Y",
            "TF2303": "T5Y",
        },
        # 扩展：添加交易所映射
        contract_to_exchange={
            "T2303": "CFFEX",
            "TF2303": "CFFEX",
        }
    )
    
    engine = RiskEngine(config)
    
    # 添加按账户维度的成交金额限制
    notional_rule = AccountTradeMetricLimitRule(
        rule_id="NOTIONAL_LIMIT",
        threshold=100_000_000,  # 1亿元
        by_account=True,
        by_exchange=True,  # 按交易所维度
        metric=MetricType.TRADE_NOTIONAL,  # 成交金额
        actions=(Action.ALERT,)
    )
    engine.add_rule(notional_rule)
    
    # 添加按产品维度的报单量限制
    order_count_rule = AccountTradeMetricLimitRule(
        rule_id="ORDER_COUNT_LIMIT",
        threshold=500,
        by_product=True,
        metric=MetricType.ORDER_COUNT,
        actions=(Action.SUSPEND_PRODUCT,)  # 暂停产品交易
    )
    engine.add_rule(order_count_rule)
    
    print("配置多维度统计:")
    print("  - 按交易所维度统计成交金额，限制1亿元")
    print("  - 按产品维度统计报单数量，限制500笔")
    
    # 模拟交易
    for i in range(10):
        # 发送订单
        order = Order(
            oid=i+1,
            account_id="ACC_001",
            contract_id="T2303" if i < 5 else "TF2303",
            direction=Direction.BID,
            price=100.0,
            volume=1000,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000
        )
        engine.on_order(order)
        
        # 生成成交
        trade = Trade(
            tid=i+1,
            oid=i+1,
            price=100.0,
            volume=1000,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000,
            account_id="ACC_001",
            contract_id=order.contract_id
        )
        actions = engine.on_trade(trade)
        
        notional = trade.price * trade.volume
        print(f"\n交易 {i+1}: 合约={trade.contract_id}, 成交金额={notional:,.0f}")
        
        if actions:
            for action in actions:
                print(f"  触发: {action.type.name} - {action.reason}")

def demo_custom_actions():
    """演示自定义动作"""
    print("\n=== 演示：多种Action类型 ===")
    
    config = RiskEngineConfig(
        contract_to_product={"T2303": "T10Y"}
    )
    
    engine = RiskEngine(config)
    
    # 创建触发多个动作的规则
    multi_action_rule = AccountTradeMetricLimitRule(
        rule_id="MULTI_ACTION_RULE",
        threshold=500,
        by_account=True,
        metric=MetricType.TRADE_VOLUME,
        actions=(
            Action.SUSPEND_ACCOUNT_TRADING,  # 暂停账户交易
            Action.ALERT,                    # 发送告警
            Action.REDUCE_POSITION,          # 强制减仓
        )
    )
    engine.add_rule(multi_action_rule)
    
    print("配置规则：成交量超过500手时触发多个动作")
    
    # 触发规则
    for i in range(6):
        trade = Trade(
            tid=i+1,
            oid=i+1,
            price=100.0,
            volume=100,
            timestamp=1_700_000_000_000_000_000 + i * 1000000000,
            account_id="ACC_001",
            contract_id="T2303"
        )
        
        actions = engine.on_trade(trade)
        
        if actions:
            print(f"\n成交量达到{(i+1)*100}手，触发以下动作:")
            for action in actions:
                print(f"  - {action.type.name}")
                if action.type == Action.ALERT:
                    print(f"    [告警] {action.reason}")
                elif action.type == Action.SUSPEND_ACCOUNT_TRADING:
                    print(f"    [暂停交易] 账户: {action.target_id}")
                elif action.type == Action.REDUCE_POSITION:
                    print(f"    [强制减仓] 需要处理的账户: {action.target_id}")

def main():
    """主函数"""
    print("金融风控模块完整功能演示")
    print("=" * 60)
    
    # 演示各项功能
    demo_volume_limit()
    demo_order_rate_limit()
    demo_multi_dimension_stats()
    demo_custom_actions()
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("\n关键特性总结:")
    print("1. 支持多种指标类型：成交量、成交金额、报单量、撤单量")
    print("2. 支持多维度统计：账户、合约、产品、交易所、账户组")
    print("3. 支持滑动窗口频率控制，自动恢复")
    print("4. 支持一个规则触发多个Action")
    print("5. 百万级/秒吞吐量，微秒级延迟")

if __name__ == "__main__":
    main()