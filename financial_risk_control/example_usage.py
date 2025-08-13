"""
Example usage of the Financial Risk Control System.
"""

import time
import json
from src import (
    RiskControlEngine,
    Order,
    Trade,
    Direction,
    ActionType,
    ConfigManager,
    RuleBuilder,
    TimeWindow
)


def basic_usage_example():
    """Basic usage example of the risk control system"""
    print("=== Basic Usage Example ===\n")
    
    # Create and start the engine
    engine = RiskControlEngine(num_workers=4)
    engine.start()
    
    # Register action handlers
    def handle_suspend_account(action):
        print(f"[ACTION] Suspending account {action.account_id}: {action.reason}")
    
    def handle_suspend_order(action):
        print(f"[ACTION] Suspending orders for account {action.account_id}: {action.reason}")
    
    engine.register_action_handler(ActionType.SUSPEND_ACCOUNT, handle_suspend_account)
    engine.register_action_handler(ActionType.SUSPEND_ORDER, handle_suspend_order)
    
    # Process some orders
    current_time = int(time.time() * 1e9)
    
    print("Processing normal orders...")
    for i in range(5):
        order = Order(
            oid=i,
            account_id="ACC_001",
            contract_id="T2303",
            direction=Direction.BID,
            price=100.0 + i * 0.1,
            volume=10,
            timestamp=current_time + i * 1e9  # 1 second apart
        )
        
        actions = engine.process_order(order)
        print(f"Order {i}: {len(actions)} actions generated")
        
        # Simulate trade execution
        trade = Trade(
            tid=i,
            oid=i,
            price=order.price,
            volume=order.volume,
            timestamp=order.timestamp + 0.5e9  # 500ms later
        )
        
        trade_actions = engine.process_trade(trade)
        print(f"Trade {i}: {len(trade_actions)} actions generated")
    
    # Display statistics
    stats = engine.get_statistics()
    print(f"\nEngine Statistics:")
    print(f"  Orders processed: {stats['engine']['orders_processed']}")
    print(f"  Trades processed: {stats['engine']['trades_processed']}")
    print(f"  Average latency: {stats['engine']['avg_latency_us']:.2f} µs")
    
    # Stop the engine
    engine.stop()
    print("\nEngine stopped.")


def volume_limit_example():
    """Example demonstrating volume limit rule"""
    print("\n=== Volume Limit Example ===\n")
    
    engine = RiskControlEngine()
    engine.start()
    
    # Register handlers
    actions_received = []
    
    def action_handler(action):
        actions_received.append(action)
        print(f"[ACTION] {action.action_type.name}: {action.reason}")
    
    for action_type in ActionType:
        engine.register_action_handler(action_type, action_handler)
    
    # Generate orders that will exceed daily volume limit
    current_time = int(time.time() * 1e9)
    account_id = "ACC_TRADER_001"
    
    print(f"Generating large volume orders for {account_id}...")
    for i in range(12):  # 12 orders of 100 volume = 1200 (exceeds 1000 limit)
        order = Order(
            oid=i,
            account_id=account_id,
            contract_id="IF2312",
            direction=Direction.BID,
            price=4000.0,
            volume=100,
            timestamp=current_time + i * 1e8  # 100ms apart
        )
        
        engine.process_order(order)
        
        # Execute trade
        trade = Trade(
            tid=i,
            oid=i,
            price=4000.0,
            volume=100,
            timestamp=order.timestamp + 5e7  # 50ms later
        )
        
        engine.process_trade(trade)
        
        # Check account metrics
        metrics = engine.get_account_metrics(account_id)
        print(f"  Order {i}: Daily volume = {metrics['daily_volume']}")
    
    print(f"\nTotal actions triggered: {len(actions_received)}")
    
    engine.stop()


def frequency_control_example():
    """Example demonstrating frequency control"""
    print("\n=== Frequency Control Example ===\n")
    
    engine = RiskControlEngine()
    engine.start()
    
    # Register handler
    def action_handler(action):
        print(f"[ACTION] {action.action_type.name} for {action.account_id}: {action.reason}")
    
    engine.register_action_handler(ActionType.SUSPEND_ORDER, action_handler)
    
    # High-frequency order submission
    current_time = int(time.time() * 1e9)
    account_id = "ACC_HFT_001"
    
    print(f"Submitting high-frequency orders for {account_id}...")
    for i in range(100):  # 100 orders in quick succession
        order = Order(
            oid=i,
            account_id=account_id,
            contract_id="IC2312",
            direction=Direction.BID if i % 2 == 0 else Direction.ASK,
            price=6000.0 + (i % 10) * 0.2,
            volume=1,
            timestamp=current_time + i * 5e6  # 5ms apart (200 orders/sec)
        )
        
        actions = engine.process_order(order)
        
        if actions:
            print(f"  Frequency limit triggered at order {i}")
            break
    
    # Check metrics
    metrics = engine.get_account_metrics(account_id)
    print(f"\nAccount metrics:")
    print(f"  Order rate: {metrics['order_rate_per_sec']:.2f} orders/second")
    
    engine.stop()


def custom_configuration_example():
    """Example using custom configuration"""
    print("\n=== Custom Configuration Example ===\n")
    
    # Create custom configuration
    config_manager = ConfigManager()
    config = config_manager.create_default_config()
    
    # Add a custom rule using RuleBuilder
    custom_rule = RuleBuilder.volume_limit_rule(
        rule_id="custom_volume_limit",
        threshold=500,  # Lower threshold
        window_hours=1,  # Hourly limit instead of daily
        actions=[ActionType.WARNING, ActionType.SUSPEND_ACCOUNT]
    )
    config.add_rule(custom_rule)
    
    # Create engine with custom config
    engine = RiskControlEngine(config=config)
    engine.start()
    
    # Register handlers
    def warning_handler(action):
        print(f"[WARNING] {action.reason}")
    
    def suspend_handler(action):
        print(f"[SUSPEND] Account {action.account_id} suspended: {action.reason}")
    
    engine.register_action_handler(ActionType.WARNING, warning_handler)
    engine.register_action_handler(ActionType.SUSPEND_ACCOUNT, suspend_handler)
    
    # Test with the custom rule
    current_time = int(time.time() * 1e9)
    
    for i in range(6):  # 6 orders of 100 volume = 600 (exceeds 500)
        order = Order(
            oid=i,
            account_id="ACC_002",
            contract_id="T2306",
            direction=Direction.ASK,
            price=99.5,
            volume=100,
            timestamp=current_time + i * 1e9
        )
        
        engine.process_order(order)
        
        trade = Trade(
            tid=i,
            oid=i,
            price=99.5,
            volume=100,
            timestamp=order.timestamp + 1e8
        )
        
        engine.process_trade(trade)
    
    engine.stop()


def save_load_configuration_example():
    """Example of saving and loading configuration"""
    print("\n=== Configuration Save/Load Example ===\n")
    
    # Create and save configuration
    config_manager = ConfigManager()
    config = config_manager.create_default_config()
    
    # Save to JSON file
    config_file = "/tmp/risk_control_config.json"
    config_manager.config = config
    config_manager.save(config_file)
    print(f"Configuration saved to {config_file}")
    
    # Load configuration from file
    new_config_manager = ConfigManager(config_file)
    print(f"Configuration loaded from {config_file}")
    
    # Display loaded rules
    print("\nLoaded rules:")
    for rule in new_config_manager.config.rules:
        print(f"  - {rule.name} (enabled: {rule.enabled}, priority: {rule.priority})")


def monitoring_example():
    """Example of system monitoring"""
    print("\n=== System Monitoring Example ===\n")
    
    engine = RiskControlEngine()
    engine.start()
    
    # Register event handler for monitoring
    def event_handler(event):
        print(f"[EVENT] {event.event_type} - {event.severity}: {event.description}")
    
    engine.register_event_handler(event_handler)
    
    # Generate some activity
    current_time = int(time.time() * 1e9)
    
    # Normal trading
    for i in range(50):
        order = Order(
            oid=i,
            account_id=f"ACC_{i % 5}",
            contract_id="T2303",
            direction=Direction.BID if i % 2 == 0 else Direction.ASK,
            price=100.0 + (i % 10) * 0.1,
            volume=20,
            timestamp=current_time + i * 1e8
        )
        
        engine.process_order(order)
        
        if i % 5 == 0:  # Some trades execute
            trade = Trade(
                tid=i,
                oid=i,
                price=order.price,
                volume=order.volume,
                timestamp=order.timestamp + 5e7
            )
            engine.process_trade(trade)
    
    # Display comprehensive statistics
    stats = engine.get_statistics()
    
    print("\n=== System Statistics ===")
    print("\nEngine Performance:")
    for key, value in stats['engine'].items():
        print(f"  {key}: {value}")
    
    print("\nRule Statistics:")
    for rule_id, rule_stats in stats['rules'].items():
        print(f"  {rule_id}:")
        print(f"    Evaluated: {rule_stats['evaluated']}")
        print(f"    Triggered: {rule_stats['triggered']}")
    
    print("\nTop Accounts by Volume:")
    top_accounts = engine.metrics_collector.get_top_accounts_by_volume(
        TimeWindow.hours(1), n=5
    )
    for account_id, volume in top_accounts:
        print(f"  {account_id}: {volume:.2f}")
    
    engine.stop()


if __name__ == "__main__":
    # Run all examples
    examples = [
        basic_usage_example,
        volume_limit_example,
        frequency_control_example,
        custom_configuration_example,
        save_load_configuration_example,
        monitoring_example
    ]
    
    for example in examples:
        example()
        print("\n" + "="*50 + "\n")
        time.sleep(0.5)  # Small delay between examples