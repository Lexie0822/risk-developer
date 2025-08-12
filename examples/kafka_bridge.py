from __future__ import annotations

# 仅作示例，运行需安装 confluent-kafka 并有可用的 Kafka 集群

import json
from risk_engine import RiskEngine, EngineConfig, Action
from risk_engine.adapters.kafka import KafkaConsumerAdapter, KafkaProducerAdapter
from risk_engine.models import Order, Trade, Direction


def decode_event(data: bytes):
    obj = json.loads(data)
    if obj.get("type") == "order":
        return Order(**obj["payload"])  # 需保证字段匹配
    if obj.get("type") == "trade":
        return Trade(**obj["payload"])  # 需保证字段匹配
    return None


def encode_action(action: Action, rule_id: str, subject: object) -> bytes:
    return json.dumps({
        "action": action.name,
        "rule": rule_id,
        "subject": getattr(subject, "__dict__", str(subject)),
    }).encode()


def main():
    consumer = KafkaConsumerAdapter({
        "bootstrap.servers": "localhost:9092",
        "group.id": "risk_engine",
        "auto.offset.reset": "earliest",
    }, ["orders_trades"])

    producer = KafkaProducerAdapter({"bootstrap.servers": "localhost:9092"})

    engine = RiskEngine(EngineConfig(), rules=[], action_sink=lambda a, r, s: producer.send("risk_actions", encode_action(a, r, s)))

    for raw in consumer.iter_messages():
        evt = decode_event(raw)
        if evt is None:
            continue
        if isinstance(evt, Order):
            engine.on_order(evt)
        elif isinstance(evt, Trade):
            engine.on_trade(evt)


if __name__ == "__main__":
    main()