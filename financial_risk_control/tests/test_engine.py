"""
Test cases for the risk control engine.
"""

import unittest
import time
import threading
from unittest.mock import Mock, patch

from src.models import Order, Trade, Direction, ActionType
from src.engine import RiskControlEngine
from src.config import ConfigManager
from src.metrics import TimeWindow


class TestRiskControlEngine(unittest.TestCase):
    """Test cases for RiskControlEngine"""
    
    def setUp(self):
        """Set up test environment"""
        self.engine = RiskControlEngine(num_workers=2)
        self.engine.start()
        time.sleep(0.1)  # Allow engine to start
    
    def tearDown(self):
        """Clean up after tests"""
        self.engine.stop()
    
    def test_basic_order_processing(self):
        """Test basic order processing"""
        order = Order(
            oid=1,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.5,
            volume=10,
            timestamp=int(time.time() * 1e9)
        )
        
        actions = self.engine.process_order(order)
        
        # Should not trigger any actions initially
        self.assertEqual(len(actions), 0)
        
        # Check statistics
        stats = self.engine.get_statistics()
        self.assertEqual(stats["engine"]["orders_processed"], 1)
        self.assertGreater(stats["engine"]["avg_latency_us"], 0)
    
    def test_volume_limit_rule(self):
        """Test volume limit rule triggers correctly"""
        # Generate orders that exceed daily volume limit (1000)
        current_time = int(time.time() * 1e9)
        
        for i in range(11):  # 11 orders of 100 volume each = 1100 total
            order = Order(
                oid=i,
                account_id="ACC_001",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=100,
                timestamp=current_time + i * 1000000  # 1ms apart
            )
            
            actions = self.engine.process_order(order)
            
            # Create corresponding trade
            trade = Trade(
                tid=i,
                oid=i,
                price=100.0,
                volume=100,
                timestamp=current_time + i * 1000000 + 500000  # 0.5ms after order
            )
            
            trade_actions = self.engine.process_trade(trade)
            
            # Check if volume limit triggered on the 11th trade
            if i == 10:
                self.assertTrue(len(trade_actions) > 0)
                self.assertEqual(trade_actions[0].action_type, ActionType.SUSPEND_ACCOUNT)
                self.assertEqual(trade_actions[0].account_id, "ACC_001")
        
        # Verify account is suspended
        self.assertIn("ACC_001", self.engine.suspended_accounts)
        
        # Try another order - should be rejected
        order = Order(
            oid=100,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0,
            volume=10,
            timestamp=current_time + 20000000
        )
        
        actions = self.engine.process_order(order)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].action_type, ActionType.SUSPEND_ACCOUNT)
    
    def test_frequency_limit_rule(self):
        """Test order frequency limit rule"""
        current_time = int(time.time() * 1e9)
        
        # Generate 60 orders in quick succession (exceeds 50/sec limit)
        actions_triggered = False
        
        for i in range(60):
            order = Order(
                oid=i,
                account_id="ACC_002",
                contract_id="T2303",
                direction=Direction.ASK,
                price=99.5,
                volume=1,
                timestamp=current_time + i * 10000000  # 10ms apart
            )
            
            actions = self.engine.process_order(order)
            
            if actions and actions[0].action_type == ActionType.SUSPEND_ORDER:
                actions_triggered = True
                self.assertEqual(actions[0].account_id, "ACC_002")
                break
        
        self.assertTrue(actions_triggered, "Frequency limit rule should have triggered")
        self.assertIn("ACC_002", self.engine.suspended_order_accounts)
    
    def test_async_processing(self):
        """Test asynchronous order and trade processing"""
        processed_orders = threading.Event()
        processed_trades = threading.Event()
        
        def action_handler(action):
            if action.metadata.get("order_id") == 1:
                processed_orders.set()
            elif action.metadata.get("trade_id") == 1:
                processed_trades.set()
        
        # Register handler
        self.engine.register_action_handler(ActionType.WARNING, action_handler)
        
        # Process order async
        order = Order(
            oid=1,
            account_id="ACC_003",
            contract_id="T2306",
            direction=Direction.BID,
            price=101.0,
            volume=5000,  # Large volume to trigger warning
            timestamp=int(time.time() * 1e9)
        )
        
        self.engine.process_order_async(order)
        
        # Process trade async
        trade = Trade(
            tid=1,
            oid=1,
            price=101.0,
            volume=5000,
            timestamp=int(time.time() * 1e9) + 1000000
        )
        
        self.engine.process_trade_async(trade)
        
        # Wait for processing
        time.sleep(0.5)
        
        # Check statistics
        stats = self.engine.get_statistics()
        self.assertGreater(stats["engine"]["orders_processed"], 0)
        self.assertGreater(stats["engine"]["trades_processed"], 0)
    
    def test_account_metrics(self):
        """Test account metrics retrieval"""
        current_time = int(time.time() * 1e9)
        
        # Generate some orders and trades
        for i in range(5):
            order = Order(
                oid=i,
                account_id="ACC_004",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=50,
                timestamp=current_time + i * 1000000000  # 1 second apart
            )
            
            self.engine.process_order(order)
            
            trade = Trade(
                tid=i,
                oid=i,
                price=100.0,
                volume=50,
                timestamp=current_time + i * 1000000000 + 500000000
            )
            
            self.engine.process_trade(trade)
        
        # Get account metrics
        metrics = self.engine.get_account_metrics("ACC_004")
        
        self.assertEqual(metrics["daily_volume"], 250.0)  # 5 trades * 50 volume
        self.assertEqual(metrics["hourly_volume"], 250.0)
        self.assertGreater(metrics["order_rate_per_sec"], 0)
        self.assertGreater(metrics["order_rate_per_min"], 0)
    
    def test_config_update(self):
        """Test configuration update"""
        config_manager = ConfigManager()
        config = config_manager.create_default_config()
        
        # Modify volume threshold
        config.rules[0].metrics[0].threshold = 500  # Lower threshold
        
        # Update engine config
        self.engine.update_config(config)
        
        # Test with new threshold
        current_time = int(time.time() * 1e9)
        
        for i in range(6):  # 6 orders of 100 volume = 600 total
            order = Order(
                oid=i,
                account_id="ACC_005",
                contract_id="T2303",
                direction=Direction.BID,
                price=100.0,
                volume=100,
                timestamp=current_time + i * 1000000
            )
            
            self.engine.process_order(order)
            
            trade = Trade(
                tid=i,
                oid=i,
                price=100.0,
                volume=100,
                timestamp=current_time + i * 1000000 + 500000
            )
            
            actions = self.engine.process_trade(trade)
            
            # Should trigger on 6th trade (total 600 > 500)
            if i == 5:
                self.assertTrue(len(actions) > 0)
                self.assertEqual(actions[0].action_type, ActionType.SUSPEND_ACCOUNT)
    
    def test_multiple_accounts(self):
        """Test handling multiple accounts simultaneously"""
        current_time = int(time.time() * 1e9)
        accounts = ["ACC_100", "ACC_101", "ACC_102"]
        
        # Generate orders for multiple accounts
        for i in range(30):
            account_id = accounts[i % 3]
            order = Order(
                oid=i,
                account_id=account_id,
                contract_id="T2303",
                direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                price=100.0 + (i % 5) * 0.1,
                volume=10,
                timestamp=current_time + i * 100000000  # 100ms apart
            )
            
            self.engine.process_order(order)
        
        # Check that metrics are tracked separately
        for account_id in accounts:
            metrics = self.engine.get_account_metrics(account_id)
            self.assertGreater(metrics["order_rate_per_min"], 0)
    
    def test_error_handling(self):
        """Test error handling in the engine"""
        # Test trade without associated order
        trade = Trade(
            tid=999,
            oid=999,  # Non-existent order
            price=100.0,
            volume=10,
            timestamp=int(time.time() * 1e9)
        )
        
        actions = self.engine.process_trade(trade)
        self.assertEqual(len(actions), 0)  # Should handle gracefully
        
        # Check statistics still updated
        stats = self.engine.get_statistics()
        self.assertGreater(stats["engine"]["trades_processed"], 0)
    
    def test_performance_metrics(self):
        """Test performance tracking"""
        current_time = int(time.time() * 1e9)
        
        # Process many orders to get stable metrics
        for i in range(100):
            order = Order(
                oid=i,
                account_id=f"ACC_{i % 10}",
                contract_id="T2303",
                direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                price=100.0,
                volume=1,
                timestamp=current_time + i * 1000000  # 1ms apart
            )
            
            self.engine.process_order(order)
        
        stats = self.engine.get_statistics()
        
        # Check performance metrics
        self.assertEqual(stats["engine"]["orders_processed"], 100)
        self.assertGreater(stats["engine"]["throughput_ops_per_sec"], 0)
        self.assertLess(stats["engine"]["avg_latency_us"], 10000)  # Should be < 10ms
        self.assertGreater(stats["engine"]["max_latency_us"], 0)


class TestEngineIntegration(unittest.TestCase):
    """Integration tests for the risk control engine"""
    
    def test_full_workflow(self):
        """Test complete order to trade workflow"""
        engine = RiskControlEngine(num_workers=4)
        engine.start()
        
        try:
            actions_received = []
            events_received = []
            
            # Register handlers
            def action_handler(action):
                actions_received.append(action)
            
            def event_handler(event):
                events_received.append(event)
            
            for action_type in ActionType:
                engine.register_action_handler(action_type, action_handler)
            
            engine.register_event_handler(event_handler)
            
            # Simulate trading session
            current_time = int(time.time() * 1e9)
            
            # Morning: Normal trading
            for i in range(20):
                order = Order(
                    oid=i,
                    account_id="ACC_TRADER_1",
                    contract_id="IF2312",
                    direction=Direction.BID if i % 2 == 0 else Direction.ASK,
                    price=4000.0 + (i % 10),
                    volume=2,
                    timestamp=current_time + i * 60 * 1e9  # 1 minute apart
                )
                
                engine.process_order(order)
                
                # Simulate partial fills
                if i % 3 == 0:
                    trade = Trade(
                        tid=i,
                        oid=i,
                        price=order.price,
                        volume=1,  # Partial fill
                        timestamp=order.timestamp + 30 * 1e9  # 30 seconds later
                    )
                    engine.process_trade(trade)
            
            # Afternoon: High frequency trading (should trigger frequency limit)
            burst_start = current_time + 3600 * 1e9  # 1 hour later
            
            for i in range(100):
                order = Order(
                    oid=100 + i,
                    account_id="ACC_HFT_1",
                    contract_id="IC2312",
                    direction=Direction.BID,
                    price=6000.0,
                    volume=1,
                    timestamp=burst_start + i * 5 * 1e6  # 5ms apart
                )
                
                engine.process_order(order)
            
            # Check results
            time.sleep(0.5)  # Allow processing to complete
            
            # Should have triggered frequency limit
            self.assertTrue(any(a.action_type == ActionType.SUSPEND_ORDER for a in actions_received))
            self.assertTrue(any(a.account_id == "ACC_HFT_1" for a in actions_received))
            
            # Should have risk events
            self.assertGreater(len(events_received), 0)
            
            # Check final statistics
            stats = engine.get_statistics()
            self.assertGreater(stats["engine"]["orders_processed"], 100)
            self.assertGreater(stats["engine"]["actions_generated"], 0)
            self.assertGreater(stats["rules"]["account_order_frequency_limit"]["triggered"], 0)
            
        finally:
            engine.stop()


if __name__ == '__main__':
    unittest.main()