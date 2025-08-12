from __future__ import annotations

# 可选 Kafka 适配器：仅在安装 confluent_kafka 时可用
# 用途：将订单/成交事件从 Kafka 拉取为迭代器，将动作写回 Kafka

from typing import Any, Callable, Iterable, Iterator, Optional

try:
    from confluent_kafka import Consumer, Producer
except Exception:  # pragma: no cover - 可选依赖
    Consumer = None  # type: ignore
    Producer = None  # type: ignore


class KafkaConsumerAdapter:
    def __init__(self, conf: dict, topics: list[str]) -> None:
        if Consumer is None:
            raise ImportError("confluent_kafka not installed. pip install confluent-kafka")
        self._consumer = Consumer(conf)
        self._consumer.subscribe(topics)

    def iter_messages(self) -> Iterator[bytes]:
        while True:
            msg = self._consumer.poll(0.01)
            if msg is None:
                continue
            if msg.error():
                # 生产中应处理错误
                continue
            yield msg.value()

    def close(self) -> None:
        self._consumer.close()


class KafkaProducerAdapter:
    def __init__(self, conf: dict) -> None:
        if Producer is None:
            raise ImportError("confluent_kafka not installed. pip install confluent-kafka")
        self._producer = Producer(conf)

    def send(self, topic: str, value: bytes) -> None:
        self._producer.produce(topic, value)
        self._producer.poll(0)

    def flush(self, timeout: float | None = None) -> None:
        self._producer.flush(timeout or 5.0)