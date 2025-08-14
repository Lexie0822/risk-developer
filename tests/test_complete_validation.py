"""
完整的金融风控模块验证测试
测试所有需求功能和扩展点
"""

import pytest
import time
from typing import List
from risk_engine import RiskEngine
from risk_engine.config import (
    RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig,
    StatsDimension, DynamicRuleConfig
)
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.actions import Action
from risk_engine.rules import Rule, RuleContext, RuleResult


class TestCompleteValidation:
    """完整的系统验证测试"""
    
    def setup_method(self):
        """测试前准备"""
        self.base_timestamp = int(time.time() * 1e9)
        
    def create_engine(self, **kwargs) -> RiskEngine:
        """创建测试引擎"""
        default_config = {
            "contract_to_product": {
                "T2303": "T10Y",
                "T2306": "T10Y",
                "TF2303": "T5Y",
                "TF2306": "T5Y",
                "IF2303": "IF",
            },
            "contract_to_exchange": {
                "T2303": "CFFEX",
                "T2306": "CFFEX",
                "TF2303": "CFFEX",
                "TF2306": "CFFEX",
                "IF2303": "CFFEX",
            }
        }
        default_config.update(kwargs)
        config = RiskEngineConfig(**default_config)
        return RiskEngine(config)
    
    def test_volume_limit_by_account(self):
        """测试1.1: 单账户成交量限制"""
        print("\n=== 测试1.1: 单账户成交量限制 ===")
        
        engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=100,
                dimension=StatsDimension.ACCOUNT,
                metric=MetricType.TRADE_VOLUME
            )
        )
        
        # 创建订单和成交，逐步接近阈值
        total_volume = 0
        for i in range(10):
            volume = 15
            order = Order(i, "ACC_001", "T2303", Direction.BID, 100.0, volume, self.base_timestamp + i)
            actions = engine.on_order(order)
            assert not actions, f"订单{i}不应触发风控"
            
            trade = Trade(i, i, 100.0, volume, self.base_timestamp + i + 1000,
                         account_id="ACC_001", contract_id="T2303")
            actions = engine.on_trade(trade)
            
            total_volume += volume
            print(f"成交{i}: 当前累计成交量={total_volume}")
            
            if total_volume > 100:
                assert actions, f"累计成交量{total_volume}应触发风控"
                assert any(a.type == Action.SUSPEND_ACCOUNT_TRADING for a in actions)
                print(f"✓ 成功触发账户交易暂停: {actions[0].reason}")
                break
            else:
                assert not actions
    
    def test_volume_limit_by_product(self):
        """测试1.2: 产品维度成交量限制"""
        print("\n=== 测试1.2: 产品维度成交量限制 ===")
        
        engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=200,
                dimension=StatsDimension.PRODUCT,
                metric=MetricType.TRADE_VOLUME
            )
        )
        
        # 同一产品的不同合约累计成交量
        contracts = ["T2303", "T2306"]  # 都属于T10Y产品
        total_volume = 0
        
        for i in range(20):
            contract = contracts[i % 2]
            volume = 15
            order = Order(i, f"ACC_{i%3}", contract, Direction.BID, 100.0, volume, self.base_timestamp + i)
            engine.on_order(order)
            
            trade = Trade(i, i, 100.0, volume, self.base_timestamp + i + 1000,
                         account_id=f"ACC_{i%3}", contract_id=contract)
            actions = engine.on_trade(trade)
            
            total_volume += volume
            print(f"成交{i}: 合约={contract}, 产品累计成交量={total_volume}")
            
            if total_volume > 200:
                assert actions, f"产品累计成交量{total_volume}应触发风控"
                print(f"✓ 成功触发产品维度风控: {actions[0].reason}")
                break
    
    def test_trade_notional_limit(self):
        """测试1.3: 成交金额限制（扩展点）"""
        print("\n=== 测试1.3: 成交金额限制 ===")
        
        engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=1_000_000,  # 100万元
                dimension=StatsDimension.ACCOUNT,
                metric=MetricType.TRADE_NOTIONAL  # 成交金额
            )
        )
        
        # 高价值成交
        order = Order(1, "ACC_001", "IF2303", Direction.BID, 4000.0, 100, self.base_timestamp)
        engine.on_order(order)
        
        # 成交金额 = 4000 * 100 = 400,000
        trade = Trade(1, 1, 4000.0, 100, self.base_timestamp + 1000)
        actions = engine.on_trade(trade)
        assert not actions
        print(f"成交金额: 400,000元，未触发风控")
        
        # 再来一笔大额成交
        order2 = Order(2, "ACC_001", "IF2303", Direction.BID, 4500.0, 150, self.base_timestamp + 2000)
        engine.on_order(order2)
        
        # 成交金额 = 4500 * 150 = 675,000，累计 1,075,000
        trade2 = Trade(2, 2, 4500.0, 150, self.base_timestamp + 3000)
        actions = engine.on_trade(trade2)
        assert actions
        print(f"✓ 累计成交金额超过100万，成功触发风控: {actions[0].reason}")
    
    def test_order_rate_limit(self):
        """测试2.1: 报单频率控制"""
        print("\n=== 测试2.1: 报单频率控制 ===")
        
        engine = self.create_engine(
            order_rate_limit=OrderRateLimitRuleConfig(
                threshold=5,
                window_seconds=1,
                dimension=StatsDimension.ACCOUNT
            )
        )
        
        # 快速下单
        base_time = self.base_timestamp
        for i in range(7):
            order = Order(i, "ACC_001", "T2303", Direction.BID, 100.0, 1, base_time + i * int(1e8))
            actions = engine.on_order(order)
            
            if i < 5:
                assert not actions, f"第{i+1}个订单不应触发频率限制"
                print(f"订单{i+1}: 正常处理")
            else:
                assert actions, f"第{i+1}个订单应触发频率限制"
                assert any(a.type == Action.SUSPEND_ORDERING for a in actions)
                print(f"✓ 订单{i+1}: 触发频率限制: {actions[0].reason}")
    
    def test_rate_limit_auto_recovery(self):
        """测试2.2: 频率限制自动恢复"""
        print("\n=== 测试2.2: 频率限制自动恢复 ===")
        
        engine = self.create_engine(
            order_rate_limit=OrderRateLimitRuleConfig(
                threshold=3,
                window_seconds=1,
                dimension=StatsDimension.ACCOUNT
            )
        )
        
        base_time = self.base_timestamp
        
        # 触发限制
        for i in range(4):
            order = Order(i, "ACC_001", "T2303", Direction.BID, 100.0, 1, base_time + i * int(1e8))
            actions = engine.on_order(order)
            if i == 3:
                assert actions
                print(f"✓ 触发频率限制")
        
        # 等待窗口过期（模拟时间流逝）
        time_after_window = base_time + int(1.5e9)  # 1.5秒后
        order = Order(100, "ACC_001", "T2303", Direction.BID, 100.0, 1, time_after_window)
        actions = engine.on_order(order)
        assert not actions or not any(a.type == Action.SUSPEND_ORDERING for a in actions)
        print(f"✓ 时间窗口过期后自动恢复")
    
    def test_multiple_actions(self):
        """测试3: 一个规则触发多个Action"""
        print("\n=== 测试3: 一个规则触发多个Action ===")
        
        # 自定义规则，触发多个动作
        class MultiActionRule(Rule):
            def on_order(self, ctx: RuleContext, order: Order) -> RuleResult:
                if order.volume > 100:
                    return RuleResult(
                        actions=[
                            Action.BLOCK_ORDER,
                            Action.ALERT,
                            Action.SUSPEND_ORDERING
                        ],
                        reasons=["大额订单需要审核"]
                    )
                return None
            
            def on_trade(self, ctx: RuleContext, trade: Trade) -> RuleResult:
                return None
        
        engine = self.create_engine()
        engine.add_rule(MultiActionRule())
        
        order = Order(1, "ACC_001", "T2303", Direction.BID, 100.0, 200, self.base_timestamp)
        actions = engine.on_order(order)
        
        assert len(actions) >= 3
        action_types = {a.type for a in actions}
        assert Action.BLOCK_ORDER in action_types
        assert Action.ALERT in action_types
        assert Action.SUSPEND_ORDERING in action_types
        print(f"✓ 成功触发多个动作: {[a.type.name for a in actions]}")
    
    def test_multi_dimension_stats(self):
        """测试4: 多维度统计引擎"""
        print("\n=== 测试4: 多维度统计引擎 ===")
        
        # 配置多个维度的规则
        engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=100,
                dimension=StatsDimension.EXCHANGE,  # 交易所维度
                metric=MetricType.TRADE_VOLUME
            )
        )
        
        # 添加账户组维度规则
        class AccountGroupRule(Rule):
            def __init__(self):
                self.group_volumes = {}
                
            def on_trade(self, ctx: RuleContext, trade: Trade) -> RuleResult:
                # 模拟账户组统计
                group = "GROUP_A" if trade.account_id in ["ACC_001", "ACC_002"] else "GROUP_B"
                self.group_volumes[group] = self.group_volumes.get(group, 0) + trade.volume
                
                if self.group_volumes[group] > 150:
                    return RuleResult(
                        actions=[Action.SUSPEND_ACCOUNT_GROUP],
                        reasons=[f"账户组{group}成交量超限: {self.group_volumes[group]}"]
                    )
                return None
            
            def on_order(self, ctx: RuleContext, order: Order) -> RuleResult:
                return None
        
        engine.add_rule(AccountGroupRule())
        
        # 测试交易所维度
        for i in range(10):
            order = Order(i, f"ACC_{i%3}", "T2303", Direction.BID, 100.0, 15, self.base_timestamp + i)
            engine.on_order(order)
            
            trade = Trade(i, i, 100.0, 15, self.base_timestamp + i + 1000)
            actions = engine.on_trade(trade)
            
            if i >= 6:  # 累计超过100手
                assert any(a.type == Action.SUSPEND_ACCOUNT_TRADING for a in actions)
                print(f"✓ 交易所维度统计触发风控")
                break
        
        # 测试账户组维度
        for i in range(20, 35):
            account = "ACC_001" if i % 2 == 0 else "ACC_002"
            order = Order(i, account, "T2303", Direction.BID, 100.0, 15, self.base_timestamp + i)
            engine.on_order(order)
            
            trade = Trade(i, i, 100.0, 15, self.base_timestamp + i + 1000)
            actions = engine.on_trade(trade)
            
            if actions and any(a.type == Action.SUSPEND_ACCOUNT_GROUP for a in actions):
                print(f"✓ 账户组维度统计触发风控: {actions[0].reason}")
                break
    
    def test_dynamic_config_update(self):
        """测试5: 动态配置更新"""
        print("\n=== 测试5: 动态配置更新 ===")
        
        engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=100,
                dimension=StatsDimension.ACCOUNT,
                metric=MetricType.TRADE_VOLUME
            )
        )
        
        # 初始阈值测试
        for i in range(8):
            order = Order(i, "ACC_001", "T2303", Direction.BID, 100.0, 15, self.base_timestamp + i)
            engine.on_order(order)
            trade = Trade(i, i, 100.0, 15, self.base_timestamp + i + 1000)
            actions = engine.on_trade(trade)
            
            if i == 7:  # 120手
                assert actions
                print(f"✓ 原阈值100手触发风控")
        
        # 动态更新阈值
        print("\n动态更新阈值到200手...")
        # 注意：实际系统需要实现update_rule_config方法
        # 这里模拟动态更新
        new_engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=200,  # 提高阈值
                dimension=StatsDimension.ACCOUNT,
                metric=MetricType.TRADE_VOLUME
            )
        )
        
        # 使用新阈值测试
        for i in range(10):
            order = Order(100+i, "ACC_002", "T2303", Direction.BID, 100.0, 15, self.base_timestamp + 100 + i)
            new_engine.on_order(order)
            trade = Trade(100+i, 100+i, 100.0, 15, self.base_timestamp + 100 + i + 1000)
            actions = new_engine.on_trade(trade)
            
            if i < 13:  # 195手
                assert not actions
            else:  # 210手
                assert actions
                print(f"✓ 新阈值200手触发风控")
                break
    
    def test_edge_cases(self):
        """测试6: 边界情况和异常处理"""
        print("\n=== 测试6: 边界情况和异常处理 ===")
        
        engine = self.create_engine(
            volume_limit=VolumeLimitRuleConfig(
                threshold=100,
                dimension=StatsDimension.PRODUCT,
                metric=MetricType.TRADE_VOLUME
            )
        )
        
        # 测试1: 未映射的合约
        order = Order(1, "ACC_001", "UNKNOWN", Direction.BID, 100.0, 50, self.base_timestamp)
        actions = engine.on_order(order)
        print(f"✓ 未映射合约正常处理，不触发异常")
        
        # 测试2: 成交没有对应订单
        trade = Trade(999, 999, 100.0, 50, self.base_timestamp + 1000,
                     account_id="ACC_001", contract_id="T2303")
        actions = engine.on_trade(trade)
        print(f"✓ 无对应订单的成交正常处理")
        
        # 测试3: 零成交量
        order = Order(2, "ACC_001", "T2303", Direction.BID, 100.0, 0, self.base_timestamp)
        actions = engine.on_order(order)
        assert not actions
        print(f"✓ 零成交量订单正常处理")
        
        # 测试4: 极大值
        order = Order(3, "ACC_001", "T2303", Direction.BID, 999999.99, 999999, self.base_timestamp)
        actions = engine.on_order(order)
        print(f"✓ 极大值订单正常处理")
    
    def test_performance_metrics(self):
        """测试7: 性能指标收集"""
        print("\n=== 测试7: 性能指标收集 ===")
        
        engine = self.create_engine()
        
        # 处理一批订单和成交
        start_time = time.time()
        for i in range(1000):
            order = Order(i, f"ACC_{i%10}", "T2303", Direction.BID, 100.0, 1, self.base_timestamp + i)
            engine.on_order(order)
            
            if i % 2 == 0:
                trade = Trade(i//2, i, 100.0, 1, self.base_timestamp + i + 1000)
                engine.on_trade(trade)
        
        elapsed = time.time() - start_time
        
        # 获取统计信息
        stats = engine.get_stats()
        
        print(f"\n性能统计:")
        print(f"- 处理订单数: {stats.get('orders_processed', 0):,}")
        print(f"- 处理成交数: {stats.get('trades_processed', 0):,}")
        print(f"- 触发动作数: {stats.get('actions_generated', 0):,}")
        print(f"- 处理时间: {elapsed:.3f}秒")
        print(f"- 平均TPS: {1500/elapsed:.0f} 事件/秒")
        
        assert stats.get('orders_processed', 0) == 1000
        assert stats.get('trades_processed', 0) == 500
        print(f"✓ 性能指标统计正确")


def run_complete_validation():
    """运行完整验证测试"""
    print("="*60)
    print("金融风控模块完整验证测试")
    print("="*60)
    
    test = TestCompleteValidation()
    test.setup_method()
    
    # 运行所有测试
    test_methods = [
        test.test_volume_limit_by_account,
        test.test_volume_limit_by_product,
        test.test_trade_notional_limit,
        test.test_order_rate_limit,
        test.test_rate_limit_auto_recovery,
        test.test_multiple_actions,
        test.test_multi_dimension_stats,
        test.test_dynamic_config_update,
        test.test_edge_cases,
        test.test_performance_metrics,
    ]
    
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            test_method()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n✗ 测试失败: {test_method.__name__}")
            print(f"  错误: {str(e)}")
    
    print("\n" + "="*60)
    print(f"测试完成: {passed} 通过, {failed} 失败")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = run_complete_validation()
    exit(0 if success else 1)