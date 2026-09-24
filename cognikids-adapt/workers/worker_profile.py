"""Worker de perfil de acessibilidade + Grafo de Conhecimento (Sprint 2/3).

Consome a fila `profile` do RabbitMQ, busca os tokens de acessibilidade de
cada aluno no core (GET read-only) e usa esse sinal para o cold start do
Grafo de Conhecimento (ver CLAUDE.md seção 5.1 e `knowledge_graph.py`) —
persistido na coleção `student_graphs` do MongoDB satélite. Publica o
resumo de domínio na fila `adaptation` para o worker de adaptação (LLM)
consultar antes de gerar a versão adaptada por criança.

Refinamento do grafo por TelemetryEvent real (acerto/latência por conceito)
ainda não está implementado — o contrato de TelemetryEvent hoje não carrega
um campo de acerto/conceito (ver `knowledge_graph.py` para o porquê).

Processo/container independente do gateway e do core — comunicação só via
fila (com o gateway), via HTTP read-only (com o core) e com banco próprio
(nunca o do core).

Uso: python worker_profile.py
"""

import asyncio
import json
import logging
import os

import aio_pika
from aio_pika import ExchangeType
from motor.motor_asyncio import AsyncIOMotorClient

from core_client import buscar_tokens_acessibilidade
from knowledge_graph import construir_grafo_cold_start, desserializar_grafo, resumo_dominio, serializar_grafo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker_profile")

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
RABBITMQ_EXCHANGE = os.environ.get("RABBITMQ_EXCHANGE", "cognikids")
SATELLITE_MONGO_URI = os.environ.get("SATELLITE_MONGO_URI", "mongodb://localhost:27018/cognikids_adapt")

QUEUE_NAME = "profile"
PROXIMA_FILA = "adaptation"
COLLECTION_NAME = "student_graphs"


async def _perfil_e_grafo_de(aluno_id: str, colecao) -> tuple[dict, dict]:
    tokens = await buscar_tokens_acessibilidade(aluno_id)
    if tokens is None:
        logger.warning("Perfil de acessibilidade indisponível para aluno_id=%s — seguindo sem tokens", aluno_id)
        tokens = {}

    documento = await colecao.find_one({"aluno_id": aluno_id})
    if documento is None:
        grafo = construir_grafo_cold_start(aluno_id, tokens)
        logger.info("Grafo cold start criado para aluno_id=%s", aluno_id)
    else:
        grafo = desserializar_grafo(documento["grafo"])

    await colecao.update_one(
        {"aluno_id": aluno_id},
        {"$set": {"aluno_id": aluno_id, "grafo": serializar_grafo(grafo)}},
        upsert=True,
    )

    return tokens, resumo_dominio(grafo, aluno_id)


async def processar_mensagem(
    mensagem: aio_pika.abc.AbstractIncomingMessage,
    exchange: aio_pika.abc.AbstractExchange,
    colecao,
) -> None:
    async with mensagem.process():
        job = json.loads(mensagem.body.decode("utf-8"))
        student_ids = job["student_ids"]

        resultados = await asyncio.gather(*[_perfil_e_grafo_de(aluno_id, colecao) for aluno_id in student_ids])
        profile_tokens_por_aluno = {aluno_id: tokens for aluno_id, (tokens, _) in zip(student_ids, resultados)}
        dominio_por_aluno = {aluno_id: dominio for aluno_id, (_, dominio) in zip(student_ids, resultados)}

        logger.info(
            "Perfis e grafos resolvidos: job_id=%s alunos=%d",
            job.get("job_id"), len(student_ids),
        )

        proxima_mensagem = {
            **job,
            "profile_tokens": profile_tokens_por_aluno,
            "knowledge_graph_summary": dominio_por_aluno,
        }
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(proxima_mensagem).encode("utf-8"),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=PROXIMA_FILA,
        )


async def main() -> None:
    cliente_mongo = AsyncIOMotorClient(SATELLITE_MONGO_URI)
    db = cliente_mongo.get_default_database()
    colecao = db[COLLECTION_NAME]

    conexao = await aio_pika.connect_robust(RABBITMQ_URL)
    async with conexao:
        canal = await conexao.channel()
        await canal.set_qos(prefetch_count=10)

        exchange = await canal.declare_exchange(RABBITMQ_EXCHANGE, ExchangeType.DIRECT, durable=True)

        fila = await canal.declare_queue(QUEUE_NAME, durable=True)
        await fila.bind(exchange, routing_key=QUEUE_NAME)

        logger.info("Worker de perfil pronto — consumindo fila '%s'", QUEUE_NAME)

        async with fila.iterator() as mensagens:
            async for mensagem in mensagens:
                try:
                    await processar_mensagem(mensagem, exchange, colecao)
                except Exception:
                    logger.exception("Falha ao processar job de perfil")


if __name__ == "__main__":
    asyncio.run(main())
