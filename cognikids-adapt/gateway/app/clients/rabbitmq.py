import json

import aio_pika
from aio_pika import ExchangeType

from app.core.config import settings

QUEUES = ["analysis", "profile", "adaptation", "telemetry"]

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_exchange: aio_pika.abc.AbstractExchange | None = None


async def connect() -> None:
    global _connection, _channel, _exchange

    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel = await _connection.channel()
    _exchange = await _channel.declare_exchange(
        settings.rabbitmq_exchange, ExchangeType.DIRECT, durable=True
    )

    for nome_fila in QUEUES:
        fila = await _channel.declare_queue(nome_fila, durable=True)
        await fila.bind(_exchange, routing_key=nome_fila)


async def close() -> None:
    if _connection is not None:
        await _connection.close()


async def publish(routing_key: str, payload: dict) -> None:
    if _exchange is None:
        raise RuntimeError("RabbitMQ não conectado — chame connect() no startup da aplicação")

    mensagem = aio_pika.Message(
        body=json.dumps(payload).encode("utf-8"),
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )
    await _exchange.publish(mensagem, routing_key=routing_key)
