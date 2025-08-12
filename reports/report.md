# 风控模块测试与性能报告

生成时间: 2025-08-12 11:41:48


## 测试结果

- 是否全部通过: 是

- 用例总数: 7

- 失败: 0, 错误: 0, 跳过: 0


<details><summary>测试输出</summary>


```
test_deterministic_action_sequence (test_e2e.E2EVerificationTests.test_deterministic_action_sequence) ... ok
test_hot_update (test_rules.RiskEngineTests.test_hot_update) ... ok
test_order_rate_limit_trigger_and_resume (test_rules.RiskEngineTests.test_order_rate_limit_trigger_and_resume) ... ok
test_persistence_roundtrip (test_rules.RiskEngineTests.test_persistence_roundtrip) ... ok
test_volume_limit_and_daily_reset (test_rules.RiskEngineTests.test_volume_limit_and_daily_reset) ... ok
test_order_rate_limit_by_product (test_rules_product.ProductDimensionTests.test_order_rate_limit_by_product) ... ok
test_volume_limit_by_product (test_rules_product.ProductDimensionTests.test_volume_limit_by_product) ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.001s

OK
```

</details>


## 演示触发的 Action

- 限频规则触发:

  - {'type': 'SUSPEND_ORDERING', 'account': 'ACC_001', 'reason': 'Order rate 6/1000000000ns exceeds 5', 'meta': {'key': ('ACC_001',), 'count': 6}}

- 成交量规则触发:

  - {'type': 'SUSPEND_ACCOUNT_TRADING', 'account': 'ACC_001', 'reason': 'Volume limit exceeded: 1200 > 1000 on account', 'meta': {'key': ('ACC_001',)}}



## 性能基准

- Orders: 200000 条，耗时 0.302813 s，吞吐 ~660473/s

- Trades: 100000 条，耗时 0.077975 s，吞吐 ~1282460/s
