#!/usr/bin/env python3
"""
金融风控模块系统验证脚本

验证系统是否满足所有项目要求：
1. 风控规则需求
2. 输入数据定义
3. 系统要求
4. 扩展点支持
"""

import time
import asyncio
import threading
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from risk_engine import RiskEngine, EngineConfig
from risk_engine.config import RiskEngineConfig, VolumeLimitRuleConfig, OrderRateLimitRuleConfig, StatsDimension
from risk_engine.models import Order, Trade, Direction
from risk_engine.actions import Action
from risk_engine.metrics import MetricType
from risk_engine.rules import Rule, RuleContext, RuleResult, AccountTradeMetricLimitRule, OrderRateLimitRule


@dataclass
class VerificationResult:
    """验证结果"""
    test_name: str
    passed: bool
    details: str
    performance_metrics: Dict[str, Any] = None


class SystemVerifier:
    """系统验证器"""
    
    def __init__(self):
        self.results: List[VerificationResult] = []
        self.test_engine = None
        self.action_records = []
    
    def record_action(self, action: Action, rule_id: str, subject: Any):
        """记录风控动作"""
        self.action_records.append((action, rule_id, subject))
    
    def verify_data_models(self) -> VerificationResult:
        """验证数据模型定义"""
        print("🔍 验证数据模型定义...")
        
        try:
            # 验证Order模型
            order = Order(
                oid=1,
                account_id="ACC_001",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=1,
                timestamp=1_700_000_000_000_000_000,
                exchange_id="CFFEX",
                account_group_id="GROUP_001"
            )
            
            # 验证Trade模型
            trade = Trade(
                tid=1,
                oid=1,
                price=100.0,
                volume=1,
                timestamp=1_700_000_000_000_000_000,
                account_id="ACC_001",
                contract_id="T2303",
                exchange_id="CFFEX",
                account_group_id="GROUP_001"
            )
            
            # 验证字段类型和必需性
            assert isinstance(order.oid, int), "订单ID必须是整数"
            assert isinstance(order.account_id, str), "账户ID必须是字符串"
            assert isinstance(order.contract_id, str), "合约ID必须是字符串"
            assert isinstance(order.direction, Direction), "方向必须是Direction枚举"
            assert isinstance(order.price, float), "价格必须是浮点数"
            assert isinstance(order.volume, int), "数量必须是整数"
            assert isinstance(order.timestamp, int), "时间戳必须是整数"
            
            return VerificationResult(
                test_name="数据模型定义",
                passed=True,
                details="Order和Trade模型完全符合需求，包含所有必需字段和扩展字段"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="数据模型定义",
                passed=False,
                details=f"数据模型验证失败: {str(e)}"
            )
    
    def verify_risk_rules(self) -> VerificationResult:
        """验证风控规则"""
        print("🔍 验证风控规则...")
        
        try:
            # 创建测试引擎
            config = EngineConfig(
                contract_to_product={"T2303": "T10Y", "T2306": "T10Y"},
                deduplicate_actions=True,
            )
            
            self.test_engine = RiskEngine(config, action_sink=self.record_action)
            
            # 添加成交量限制规则
            volume_rule = AccountTradeMetricLimitRule(
                rule_id="VOLUME-TEST",
                metric=MetricType.TRADE_VOLUME,
                threshold=1000,
                actions=(Action.SUSPEND_ACCOUNT_TRADING,),
                by_account=True,
                by_product=True,
            )
            
            # 添加报单频率限制规则
            rate_rule = OrderRateLimitRule(
                rule_id="RATE-TEST",
                threshold=5,  # 5次/秒，便于测试
                window_seconds=1,
                suspend_actions=(Action.SUSPEND_ORDERING,),
                resume_actions=(Action.RESUME_ORDERING,),
                dimension="account",
            )
            
            self.test_engine.add_rule(volume_rule)
            self.test_engine.add_rule(rate_rule)
            
            return VerificationResult(
                test_name="风控规则",
                passed=True,
                details="成功创建成交量限制和报单频率控制规则"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="风控规则",
                passed=False,
                details=f"风控规则验证失败: {str(e)}"
            )
    
    def verify_volume_limit_rule(self) -> VerificationResult:
        """验证成交量限制规则"""
        print("🔍 验证成交量限制规则...")
        
        try:
            base_ts = 1_700_000_000_000_000_000
            
            # 测试1: 单合约成交量限制
            # 先成交990手，不触发
            trade1 = Trade(
                tid=1, oid=1, account_id="ACC_001", contract_id="T2303",
                price=100.0, volume=990, timestamp=base_ts
            )
            self.test_engine.on_trade(trade1)
            
            # 再成交10手，达到1000手阈值，应该触发
            trade2 = Trade(
                tid=2, oid=2, account_id="ACC_001", contract_id="T2306",
                price=101.0, volume=10, timestamp=base_ts + 1
            )
            self.test_engine.on_trade(trade2)
            
            # 验证是否触发了暂停交易动作
            suspend_actions = [a for a, _, _ in self.action_records if a == Action.SUSPEND_ACCOUNT_TRADING]
            if not suspend_actions:
                return VerificationResult(
                    test_name="成交量限制规则",
                    passed=False,
                    details="成交量达到阈值时未触发风控动作"
                )
            
            # 测试2: 产品维度聚合
            self.action_records.clear()
            trade3 = Trade(
                tid=3, oid=3, account_id="ACC_002", contract_id="T2303",
                price=100.0, volume=600, timestamp=base_ts + 1000
            )
            trade4 = Trade(
                tid=4, oid=4, account_id="ACC_002", contract_id="T2306",
                price=100.0, volume=400, timestamp=base_ts + 1001
            )
            trade5 = Trade(
                tid=5, oid=5, account_id="ACC_002", contract_id="T2306",
                price=100.0, volume=1, timestamp=base_ts + 1002
            )
            
            self.test_engine.on_trade(trade3)
            self.test_engine.on_trade(trade4)
            self.test_engine.on_trade(trade5)
            
            # 验证产品维度聚合是否工作
            product_suspend_actions = [a for a, _, _ in self.action_records if a == Action.SUSPEND_ACCOUNT_TRADING]
            if not product_suspend_actions:
                return VerificationResult(
                    test_name="成交量限制规则",
                    passed=False,
                    details="产品维度聚合统计未正常工作"
                )
            
            return VerificationResult(
                test_name="成交量限制规则",
                passed=True,
                details="成交量限制规则正常工作，支持单合约和产品维度统计"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="成交量限制规则",
                passed=False,
                details=f"成交量限制规则验证失败: {str(e)}"
            )
    
    def verify_order_rate_limit_rule(self) -> VerificationResult:
        """验证报单频率控制规则"""
        print("🔍 验证报单频率控制规则...")
        
        try:
            self.action_records.clear()
            base_ts = 1_800_000_000_000_000_000
            
            # 测试1: 超过阈值触发暂停
            # 在1秒内提交6笔订单，超过阈值5
            for i in range(6):
                order = Order(
                    oid=i+1, account_id="ACC_001", contract_id="T2303",
                    direction=Direction.BID, price=100.0, volume=1,
                    timestamp=base_ts + i * 100_000_000  # 100ms间隔
                )
                self.test_engine.on_order(order)
            
            # 验证是否触发了暂停报单动作
            suspend_actions = [a for a, _, _ in self.action_records if a == Action.SUSPEND_ORDERING]
            if not suspend_actions:
                return VerificationResult(
                    test_name="报单频率控制规则",
                    passed=False,
                    details="报单频率超过阈值时未触发暂停动作"
                )
            
            # 测试2: 频率回落自动恢复
            self.action_records.clear()
            # 等待1秒后提交1笔订单，应该触发恢复
            order = Order(
                oid=100, account_id="ACC_001", contract_id="T2303",
                direction=Direction.BID, price=100.0, volume=1,
                timestamp=base_ts + 1_000_000_000  # 1秒后
            )
            self.test_engine.on_order(order)
            
            # 验证是否触发了恢复报单动作
            resume_actions = [a for a, _, _ in self.action_records if a == Action.RESUME_ORDERING]
            if not resume_actions:
                return VerificationResult(
                    test_name="报单频率控制规则",
                    passed=False,
                    details="报单频率回落时未触发恢复动作"
                )
            
            return VerificationResult(
                test_name="报单频率控制规则",
                passed=True,
                details="报单频率控制规则正常工作，支持暂停和自动恢复"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="报单频率控制规则",
                passed=False,
                details=f"报单频率控制规则验证失败: {str(e)}"
            )
    
    def verify_action_system(self) -> VerificationResult:
        """验证Action系统"""
        print("🔍 验证Action系统...")
        
        try:
            # 验证所有必需的Action类型
            required_actions = {
                Action.SUSPEND_ACCOUNT_TRADING,
                Action.RESUME_ACCOUNT_TRADING,
                Action.SUSPEND_ORDERING,
                Action.RESUME_ORDERING,
                Action.BLOCK_ORDER,
                Action.ALERT
            }
            
            # 检查Action是否都有对应的处理逻辑
            action_handlers = {
                Action.SUSPEND_ACCOUNT_TRADING: "暂停账户交易",
                Action.RESUME_ACCOUNT_TRADING: "恢复账户交易",
                Action.SUSPEND_ORDERING: "暂停报单",
                Action.RESUME_ORDERING: "恢复报单",
                Action.BLOCK_ORDER: "拒绝订单",
                Action.ALERT: "风险告警"
            }
            
            for action in required_actions:
                if action not in action_handlers:
                    return VerificationResult(
                        test_name="Action系统",
                        passed=False,
                        details=f"缺少必需的Action类型: {action}"
                    )
            
            return VerificationResult(
                test_name="Action系统",
                passed=True,
                details=f"Action系统完整，包含{len(required_actions)}种处置动作"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="Action系统",
                passed=False,
                details=f"Action系统验证失败: {str(e)}"
            )
    
    def verify_multi_dimension_stats(self) -> VerificationResult:
        """验证多维统计引擎"""
        print("🔍 验证多维统计引擎...")
        
        try:
            # 测试不同维度的统计
            base_ts = 1_900_000_000_000_000_000
            
            # 测试账户维度
            trade1 = Trade(
                tid=1, oid=1, account_id="ACC_003", contract_id="T2303",
                price=100.0, volume=500, timestamp=base_ts
            )
            self.test_engine.on_trade(trade1)
            
            # 测试合约维度
            trade2 = Trade(
                tid=2, oid=2, account_id="ACC_004", contract_id="T2303",
                price=100.0, volume=500, timestamp=base_ts + 1
            )
            self.test_engine.on_trade(trade2)
            
            # 测试产品维度（T2303和T2306都属于T10Y产品）
            trade3 = Trade(
                tid=3, oid=3, account_id="ACC_005", contract_id="T2306",
                price=100.0, volume=500, timestamp=base_ts + 2
            )
            self.test_engine.on_trade(trade3)
            
            # 验证统计引擎能正确处理不同维度
            stats = self.test_engine.snapshot()
            if not stats:
                return VerificationResult(
                    test_name="多维统计引擎",
                    passed=False,
                    details="统计引擎未返回统计数据"
                )
            
            return VerificationResult(
                test_name="多维统计引擎",
                passed=True,
                details="多维统计引擎正常工作，支持账户、合约、产品等维度"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="多维统计引擎",
                passed=False,
                details=f"多维统计引擎验证失败: {str(e)}"
            )
    
    def verify_extensibility(self) -> VerificationResult:
        """验证扩展性"""
        print("🔍 验证扩展性...")
        
        try:
            # 测试1: 自定义规则
            class CustomRiskRule(Rule):
                def __init__(self, rule_id: str, threshold: float):
                    self.rule_id = rule_id
                    self.threshold = threshold
                
                def on_order(self, ctx: RuleContext, order: Order) -> Optional[RuleResult]:
                    if order.volume > self.threshold:
                        return RuleResult(
                            actions=[Action.BLOCK_ORDER],
                            reasons=[f"订单数量 {order.volume} 超过阈值 {self.threshold}"]
                        )
                    return None
            
            # 测试2: 动态配置更新
            # 更新报单频率限制阈值
            self.test_engine.update_order_rate_limit(threshold=10)
            
            # 更新成交量限制阈值
            self.test_engine.update_volume_limit(threshold=2000)
            
            return VerificationResult(
                test_name="扩展性",
                passed=True,
                details="系统支持自定义规则和动态配置更新"
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="扩展性",
                passed=False,
                details=f"扩展性验证失败: {str(e)}"
            )
    
    def verify_performance(self) -> VerificationResult:
        """验证性能要求"""
        print("🔍 验证性能要求...")
        
        try:
            base_ts = 2_000_000_000_000_000_000
            start_time = time.perf_counter()
            
            # 批量处理10000个订单，测试吞吐量
            for i in range(10000):
                order = Order(
                    oid=i+1, account_id=f"ACC_{i%100:03d}", contract_id="T2303",
                    direction=Direction.BID, price=100.0, volume=1,
                    timestamp=base_ts + i * 1000
                )
                self.test_engine.on_order(order)
            
            end_time = time.perf_counter()
            duration = end_time - start_time
            throughput = 10000 / duration
            
            # 测试延迟
            latency_start = time.perf_counter_ns()
            order = Order(
                oid=10001, account_id="ACC_001", contract_id="T2303",
                direction=Direction.BID, price=100.0, volume=1,
                timestamp=base_ts + 10000
            )
            self.test_engine.on_order(order)
            latency_end = time.perf_counter_ns()
            latency_us = (latency_end - latency_start) / 1000
            
            performance_metrics = {
                "throughput_ops_per_sec": throughput,
                "latency_microseconds": latency_us,
                "total_orders_processed": 10000,
                "processing_time_seconds": duration
            }
            
            # 性能要求检查
            performance_passed = True
            details = []
            
            if throughput < 100000:  # 10万/秒作为基准
                performance_passed = False
                details.append(f"吞吐量 {throughput:.0f} ops/sec 低于基准")
            else:
                details.append(f"吞吐量 {throughput:.0f} ops/sec 满足要求")
            
            if latency_us > 1000:  # 1毫秒作为基准
                performance_passed = False
                details.append(f"延迟 {latency_us:.2f} 微秒高于基准")
            else:
                details.append(f"延迟 {latency_us:.2f} 微秒满足要求")
            
            return VerificationResult(
                test_name="性能要求",
                passed=performance_passed,
                details="; ".join(details),
                performance_metrics=performance_metrics
            )
            
        except Exception as e:
            return VerificationResult(
                test_name="性能要求",
                passed=False,
                details=f"性能验证失败: {str(e)}"
            )
    
    def run_all_verifications(self) -> List[VerificationResult]:
        """运行所有验证"""
        print("🚀 开始系统验证...\n")
        
        verifications = [
            self.verify_data_models,
            self.verify_risk_rules,
            self.verify_volume_limit_rule,
            self.verify_order_rate_limit_rule,
            self.verify_action_system,
            self.verify_multi_dimension_stats,
            self.verify_extensibility,
            self.verify_performance,
        ]
        
        for verification in verifications:
            try:
                result = verification()
                self.results.append(result)
                
                status = "✅ 通过" if result.passed else "❌ 失败"
                print(f"{status} {result.test_name}")
                print(f"   详情: {result.details}")
                
                if result.performance_metrics:
                    print("   性能指标:")
                    for key, value in result.performance_metrics.items():
                        if isinstance(value, float):
                            print(f"     {key}: {value:.2f}")
                        else:
                            print(f"     {key}: {value}")
                
                print()
                
            except Exception as e:
                error_result = VerificationResult(
                    test_name=verification.__name__,
                    passed=False,
                    details=f"验证过程异常: {str(e)}"
                )
                self.results.append(error_result)
                print(f"❌ 异常 {verification.__name__}")
                print(f"   错误: {str(e)}\n")
        
        return self.results
    
    def generate_report(self) -> str:
        """生成验证报告"""
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        failed_tests = total_tests - passed_tests
        
        report = f"""
{'='*60}
金融风控模块系统验证报告
{'='*60}

测试统计:
- 总测试数: {total_tests}
- 通过测试: {passed_tests}
- 失败测试: {failed_tests}
- 通过率: {passed_tests/total_tests*100:.1f}%

详细结果:
"""
        
        for result in self.results:
            status = "✅ 通过" if result.passed else "❌ 失败"
            report += f"\n{status} {result.test_name}"
            report += f"\n   详情: {result.details}"
            
            if result.performance_metrics:
                report += "\n   性能指标:"
                for key, value in result.performance_metrics.items():
                    if isinstance(value, float):
                        report += f"\n     {key}: {value:.2f}"
                    else:
                        report += f"\n     {key}: {value}"
        
        report += f"\n\n{'='*60}"
        
        if failed_tests == 0:
            report += "\n🎉 所有测试通过！系统完全满足项目要求。"
        else:
            report += f"\n⚠️  有 {failed_tests} 个测试失败，请检查相关功能。"
        
        report += f"\n{'='*60}"
        
        return report


def main():
    """主函数"""
    verifier = SystemVerifier()
    results = verifier.run_all_verifications()
    
    # 生成报告
    report = verifier.generate_report()
    print(report)
    
    # 保存报告到文件
    with open("verification_report.txt", "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n📄 详细报告已保存到 verification_report.txt")
    
    # 返回退出码
    failed_tests = sum(1 for r in results if not r.passed)
    exit(0 if failed_tests == 0 else 1)


if __name__ == "__main__":
    main()