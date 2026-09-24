"""Worker de análise de texto (Sprint 2).

Consome a fila `analysis` do RabbitMQ, aplica Text Mining PT-BR sem LLM
(complexidade + Bloom's + Simpson's — ver ADR-006 no CLAUDE.md) sobre o
texto da atividade, e publica o resultado na fila `profile` para o próximo
worker consultar o Grafo de Conhecimento de cada aluno. Processo/container
independente do gateway — comunicação só via fila.

Uso: python worker_analysis.py
"""

import asyncio
import json
import logging
import os

import aio_pika
from aio_pika import ExchangeType

from text_mining_pt import analisar_atividade

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker_analysis")

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
RABBITMQ_EXCHANGE = os.environ.get("RABBITMQ_EXCHANGE", "cognikids")

QUEUE_NAME = "analysis"
PROXIMA_FILA = "profile"


async def processar_mensagem(
    mensagem: aio_pika.abc.AbstractIncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
) -> None:
    async with mensagem.process():
        job = json.loads(mensagem.body.decode("utf-8"))
        analise = analisar_atividade(job["original_content"])

        logger.info(
            "Análise concluída: job_id=%s bloom=%s simpson=%s",
            job.get("job_id"), analise["intencao_pedagogica_bloom"], analise["demanda_psicomotora_simpson"],
        )

        proxima_mensagem = {**job, "analysis": analise}
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(proxima_mensagem).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=PROXIMA_FILA,
        )


async def main() -> None:
    conexao = await aio_pika.connect_robust(RABBITMQ_URL)
    async with conexao:
        canal = await conexao.channel()
        await canal.set_qos(prefetch_count=10)

        exchange = await canal.declare_exchange(RABBITMQ_EXCHANGE, ExchangeType.DIRECT, durable=True)

        fila = await canal.declare_queue(QUEUE_NAME, durable=True)
        await fila.bind(exchange, routing_key=QUEUE_NAME)

        logger.info("Worker de análise pronto — consumindo fila '%s'", QUEUE_NAME)

        async with fila.iterator() as mensagens:
            async for mensagem in mensagens:
                try:
                    await processar_mensagem(mensagem, exchange)
                except Exception:
                    logger.exception("Falha ao processar job de análise")


if __name__ == "__main__":
    asyncio.run(main())
