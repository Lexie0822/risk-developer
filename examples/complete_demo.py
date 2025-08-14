#!/usr/bin/env python3
"""
金融风控模块综合示例程序
展示系统的完整功能和使用方法
"""

import asyncio
import time
import random
from datetime import datetime
from typing import List, Dict

from risk_engine import RiskEngine
from risk_engine.async_engine import create_async_engine
from risk_engine.config import (
    RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig,
    StatsDimension, DynamicRuleConfig
)
from risk_engine.models import Order, Trade, Direction
from risk_engine.metrics import MetricType
from risk_engine.actions import Action
from risk_engine.rules import Rule, RuleContext, RuleResult


class CompleteDemo:
    """完整功能演示类"""
    
    def __init__(self):
        self.base_timestamp = int(time.time() * 1e9)
        self.order_id = 0
        self.trade_id = 0
        
        # 模拟市场数据
        self.contracts = {
            "T2303": {"product": "T10Y", "exchange": "CFFEX", "base_price": 100.0},
            "T2306": {"product": "T10Y", "exchange": "CFFEX", "base_price": 100.5},
            "TF2303": {"product": "T5Y", "exchange": "CFFEX", "base_price": 99.0},
            "IF2303": {"product": "IF", "exchange": "CFFEX", "base_price": 4000.0},
        }
        
        self.accounts = ["ACC_001", "ACC_002", "ACC_003", "ACC_VIP"]
        
    def create_config(self) -> RiskEngineConfig:
        """创建引擎配置"""
        return RiskEngineConfig(
            # 合约到产品映射
            contract_to_product={k: v["product"] for k, v in self.contracts.items()},
            contract_to_exchange={k: v["exchange"] for k, v in self.contracts.items()},
            
            # 成交量限制规则
            volume_limit=VolumeLimitRuleConfig(
                threshold=1000,  # 1000手
                dimension=StatsDimension.PRODUCT,
                metric=MetricType.TRADE_VOLUME
            ),
            
            # 报单频率限制规则
            order_rate_limit=OrderRateLimitRuleConfig(
                threshold=20,  # 20次/秒
                window_seconds=1,
                dimension=StatsDimension.ACCOUNT
            ),
            
            # 性能优化参数
            num_shards=128,
            worker_threads=4
        )
    
    def generate_order(self, account: str, contract: str, volume: int = None) -> Order:
        """生成模拟订单"""
        self.order_id += 1
        contract_info = self.contracts[contract]
        
        # 价格在基准价格上下波动
        price = contract_info["base_price"] * (1 + random.uniform(-0.01, 0.01))
        
        # 成交量随机或指定
        if volume is None:
            volume = random.randint(1, 50)
        
        # 买卖方向随机
        direction = random.choice([Direction.BID, Direction.ASK])
        
        return Order(
            oid=self.order_id,
            account_id=account,
            contract_id=contract,
            direction=direction,
            price=round(price, 2),
            volume=volume,
            timestamp=self.base_timestamp + self.order_id * int(1e6)
        )
    
    def generate_trade(self, order: Order, fill_ratio: float = 1.0) -> Trade:
        """生成模拟成交"""
        self.trade_id += 1
        
        # 部分成交
        trade_volume = int(order.volume * fill_ratio)
        
        return Trade(
            tid=self.trade_id,
            oid=order.oid,
            price=order.price,
            volume=trade_volume,
            timestamp=order.timestamp + int(1e6),
            account_id=order.account_id,
            contract_id=order.contract_id
        )
    
    def demo_basic_usage(self):
        """演示1: 基本使用"""
        print("\n" + "="*60)
        print("演示1: 基本使用")
        print("="*60)
        
        # 创建引擎
        config = self.create_config()
        engine = RiskEngine(config)
        
        # 处理单个订单
        order = self.generate_order("ACC_001", "T2303", 10)
        print(f"\n提交订单: {order.account_id}, {order.contract_id}, "
              f"{order.direction.value}, {order.volume}手 @ {order.price}")
        
        actions = engine.on_order(order)
        if actions:
            print(f"触发风控动作: {[a.type.name for a in actions]}")
        else:
            print("订单通过风控检查")
        
        # 处理成交
        trade = self.generate_trade(order)
        print(f"\n成交: {trade.volume}手 @ {trade.price}")
        
        actions = engine.on_trade(trade)
        if actions:
            print(f"触发风控动作: {[a.type.name for a in actions]}")
        else:
            print("成交通过风控检查")
        
        # 获取统计
        stats = engine.get_stats()
        print(f"\n当前统计:")
        print(f"- 订单处理: {stats.get('orders_processed', 0)}")
        print(f"- 成交处理: {stats.get('trades_processed', 0)}")
    
    def demo_volume_limit(self):
        """演示2: 成交量限制"""
        print("\n" + "="*60)
        print("演示2: 成交量限制（产品维度）")
        print("="*60)
        
        config = self.create_config()
        engine = RiskEngine(config)
        
        # 模拟多个账户在同一产品上交易
        total_volume = 0
        contracts = ["T2303", "T2306"]  # 同属T10Y产品
        
        print(f"\n产品T10Y的成交量限制: 1000手")
        print("模拟多个账户交易...")
        
        for i in range(30):
            account = self.accounts[i % len(self.accounts)]
            contract = contracts[i % len(contracts)]
            volume = random.randint(30, 80)
            
            order = self.generate_order(account, contract, volume)
            engine.on_order(order)
            
            trade = self.generate_trade(order)
            actions = engine.on_trade(trade)
            
            total_volume += trade.volume
            
            print(f"\n[{i+1}] {account} 在 {contract} 成交 {trade.volume}手")
            print(f"产品T10Y累计成交量: {total_volume}手")
            
            if actions:
                print(f">>> 触发风控: {actions[0].type.name}")
                print(f">>> 原因: {actions[0].reason}")
                break
    
    def demo_rate_limit(self):
        """演示3: 报单频率限制"""
        print("\n" + "="*60)
        print("演示3: 报单频率限制")
        print("="*60)
        
        config = self.create_config()
        engine = RiskEngine(config)
        
        account = "ACC_002"
        print(f"\n账户{account}的报单频率限制: 20次/秒")
        print("模拟快速下单...")
        
        # 在短时间内快速下单
        base_time = self.base_timestamp
        for i in range(25):
            order = Order(
                oid=1000 + i,
                account_id=account,
                contract_id="IF2303",
                direction=Direction.BID,
                price=4000.0,
                volume=1,
                timestamp=base_time + i * int(5e7)  # 50ms间隔
            )
            
            actions = engine.on_order(order)
            
            if actions:
                print(f"\n订单{i+1}: 触发频率限制!")
                print(f"动作: {actions[0].type.name}")
                print(f"原因: {actions[0].reason}")
                break
            else:
                print(f"订单{i+1}: 正常处理")
    
    def demo_multi_metric(self):
        """演示4: 多指标监控"""
        print("\n" + "="*60)
        print("演示4: 多指标监控（成交金额）")
        print("="*60)
        
        # 配置成交金额限制
        config = RiskEngineConfig(
            contract_to_product={k: v["product"] for k, v in self.contracts.items()},
            volume_limit=VolumeLimitRuleConfig(
                threshold=10_000_000,  # 1000万元
                dimension=StatsDimension.ACCOUNT,
                metric=MetricType.TRADE_NOTIONAL  # 成交金额
            )
        )
        
        engine = RiskEngine(config)
        
        account = "ACC_VIP"
        print(f"\n账户{account}的成交金额限制: 1000万元")
        print("模拟大额交易...")
        
        total_notional = 0
        
        # 模拟股指期货大额交易
        for i in range(5):
            volume = random.randint(50, 200)
            order = self.generate_order(account, "IF2303", volume)
            engine.on_order(order)
            
            trade = self.generate_trade(order)
            actions = engine.on_trade(trade)
            
            notional = trade.price * trade.volume
            total_notional += notional
            
            print(f"\n交易{i+1}: {trade.volume}手 @ {trade.price}")
            print(f"本笔金额: {notional:,.0f}元")
            print(f"累计金额: {total_notional:,.0f}元")
            
            if actions:
                print(f">>> 触发风控: {actions[0].type.name}")
                print(f">>> 原因: {actions[0].reason}")
                break
    
    def demo_custom_rule(self):
        """演示5: 自定义规则"""
        print("\n" + "="*60)
        print("演示5: 自定义规则")
        print("="*60)
        
        # 自定义规则：大额订单预警
        class LargeOrderAlertRule(Rule):
            def __init__(self, alert_threshold: int):
                self.alert_threshold = alert_threshold
                
            def on_order(self, ctx: RuleContext, order: Order) -> RuleResult:
                if order.volume >= self.alert_threshold:
                    # 大额订单触发多个动作
                    return RuleResult(
                        actions=[Action.ALERT, Action.BLOCK_ORDER],
                        reasons=[f"大额订单: {order.volume}手超过阈值{self.alert_threshold}手"],
                        metadata={"order_volume": order.volume}
                    )
                return None
            
            def on_trade(self, ctx: RuleContext, trade: Trade) -> RuleResult:
                return None
        
        config = self.create_config()
        engine = RiskEngine(config)
        
        # 添加自定义规则
        engine.add_rule(LargeOrderAlertRule(alert_threshold=100))
        
        print("\n添加自定义规则: 大额订单预警（阈值100手）")
        
        # 测试不同大小的订单
        test_volumes = [50, 80, 120, 200]
        
        for volume in test_volumes:
            order = self.generate_order("ACC_003", "T2303", volume)
            print(f"\n提交订单: {volume}手")
            
            actions = engine.on_order(order)
            if actions:
                print(f"触发动作: {[a.type.name for a in actions]}")
                print(f"原因: {actions[0].reason}")
            else:
                print("订单正常通过")
    
    async def demo_async_performance(self):
        """演示6: 异步高性能处理"""
        print("\n" + "="*60)
        print("演示6: 异步高性能处理")
        print("="*60)
        
        config = self.create_config()
        engine = create_async_engine(config)
        
        await engine.start()
        
        print("\n模拟高频交易场景...")
        print("批量提交1000个订单...")
        
        start_time = time.time()
        
        # 批量生成订单
        orders = []
        for i in range(1000):
            account = self.accounts[i % len(self.accounts)]
            contract = list(self.contracts.keys())[i % len(self.contracts)]
            order = self.generate_order(account, contract)
            orders.append(engine.submit_order(order))
        
        # 并发处理
        await asyncio.gather(*orders)
        
        # 模拟部分成交
        trades = []
        for i in range(0, 1000, 2):  # 50%成交率
            trade = Trade(
                tid=5000 + i,
                oid=self.order_id - 999 + i,
                price=100.0,
                volume=10,
                timestamp=self.base_timestamp + i * int(1e6)
            )
            trades.append(engine.submit_trade(trade))
        
        await asyncio.gather(*trades)
        
        elapsed = time.time() - start_time
        
        # 获取统计
        stats = engine.get_stats()
        
        print(f"\n处理完成!")
        print(f"- 处理时间: {elapsed:.3f}秒")
        print(f"- 订单处理: {stats['orders_processed']:,}")
        print(f"- 成交处理: {stats['trades_processed']:,}")
        print(f"- 吞吐量: {1500/elapsed:,.0f} 事件/秒")
        
        await engine.stop()
    
    def demo_monitoring(self):
        """演示7: 监控和统计"""
        print("\n" + "="*60)
        print("演示7: 监控和统计")
        print("="*60)
        
        config = self.create_config()
        engine = RiskEngine(config)
        
        print("\n处理一批混合交易...")
        
        # 模拟一段时间的交易
        for i in range(100):
            # 随机选择账户和合约
            account = random.choice(self.accounts)
            contract = random.choice(list(self.contracts.keys()))
            
            # 生成订单
            order = self.generate_order(account, contract)
            engine.on_order(order)
            
            # 80%的订单成交
            if random.random() < 0.8:
                trade = self.generate_trade(order, fill_ratio=random.uniform(0.5, 1.0))
                engine.on_trade(trade)
        
        # 获取详细统计
        stats = engine.get_stats()
        
        print(f"\n系统统计信息:")
        print(f"- 订单总数: {stats.get('orders_processed', 0):,}")
        print(f"- 成交总数: {stats.get('trades_processed', 0):,}")
        print(f"- 触发动作: {stats.get('actions_generated', 0):,}")
        
        # 获取当前活跃规则
        print(f"\n活跃规则:")
        print(f"- 成交量限制: 产品维度, 阈值1000手")
        print(f"- 频率限制: 账户维度, 阈值20次/秒")
    
    def run_all_demos(self):
        """运行所有演示"""
        print("="*60)
        print("金融风控模块 - 完整功能演示")
        print("="*60)
        print(f"\n开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 同步演示
        self.demo_basic_usage()
        time.sleep(0.5)
        
        self.demo_volume_limit()
        time.sleep(0.5)
        
        self.demo_rate_limit()
        time.sleep(0.5)
        
        self.demo_multi_metric()
        time.sleep(0.5)
        
        self.demo_custom_rule()
        time.sleep(0.5)
        
        # 异步演示
        asyncio.run(self.demo_async_performance())
        time.sleep(0.5)
        
        self.demo_monitoring()
        
        print("\n" + "="*60)
        print("演示完成!")
        print("="*60)


def main():
    """主函数"""
    demo = CompleteDemo()
    
    # 运行所有演示
    demo.run_all_demos()
    
    # 显示使用提示
    print("\n使用提示:")
    print("1. 本演示展示了风控系统的所有核心功能")
    print("2. 可以根据需要修改配置参数进行测试")
    print("3. 查看 tests/test_complete_validation.py 了解更多测试用例")
    print("4. 查看 bench_async.py 进行性能基准测试")


if __name__ == "__main__":
    main()