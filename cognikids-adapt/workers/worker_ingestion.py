"""Worker de ingestão de telemetria (Sprint 1) + refinamento do Grafo de
Conhecimento (Sprint 3).

Consome a fila `telemetry` do RabbitMQ e persiste cada evento na coleção
`telemetry_events` do MongoDB satélite. Quando o evento é um
`step_completed` avaliável (carrega `concept` + `correct` — ver
`gateway/app/schemas/telemetry.py`), também atualiza a aresta do Grafo de
Conhecimento daquele aluno-conceito (`knowledge_graph.py`), na mesma
coleção `student_graphs` que `worker_profile.py` lê no cold start — é assim
que o loop de realimentação da seção 5.1 do CLAUDE.md se fecha: uso real
refina o grafo, a próxima adaptação já nasce ajustada.

Processo/container independente do gateway — comunicação só via fila, sem
import de código do gateway.

Uso: python worker_ingestion.py
"""

import asyncio
import datetime
import json
import logging
import os

import aio_pika
from aio_pika import ExchangeType
from motor.motor_asyncio import AsyncIOMotorClient

from knowledge_graph import atualizar_aresta_grafo, desserializar_grafo, serializar_grafo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("worker_ingestion")

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
RABBITMQ_EXCHANGE = os.environ.get("RABBITMQ_EXCHANGE", "cognikids")
SATELLITE_MONGO_URI = os.environ.get("SATELLITE_MONGO_URI", "mongodb://localhost:27018/cognikids_adapt")

QUEUE_NAME = "telemetry"
TELEMETRY_COLLECTION = "telemetry_events"
GRAPH_COLLECTION = "student_graphs"

# Nao ha finalidade legitima para manter o log bruto de telemetria (inclui
# `concept`/`correct`, sinal comportamental de uma crianca) indefinidamente
# — o que importa a longo prazo ja fica agregado no Grafo de Conhecimento
# (colecao `student_graphs`, sem TTL: e' estado atual, nao log). Auditoria
# de LGPD encontrou retencao indefinida aqui.
RETENCAO_TELEMETRIA_DIAS = 180


async def _refinar_grafo_se_aplicavel(evento: dict, colecao_grafos) -> None:
    """Atualiza a aresta aluno-conceito quando o evento traz sinal avaliável.

    Só se aplica a step_completed com concept+correct presentes — nem todo
    passo tem resposta certa/errada (ver docstring de TelemetryEvent).
    """
    if evento.get("event_type") != "step_completed":
        return
    conceito = evento.get("concept")
    acertou = evento.get("correct")
    if conceito is None or acertou is None:
        return

    aluno_id = evento["student_id"]
    documento = await colecao_grafos.find_one({"aluno_id": aluno_id})
    if documento is None:
        logger.warning(
            "Evento com concept/correct para aluno_id=%s sem grafo existente (cold start ainda "
            "não rodou) — ignorando refinamento", aluno_id,
        )
        return

    grafo = desserializar_grafo(documento["grafo"])
    grafo = atualizar_aresta_grafo(grafo, aluno_id, conceito, acertou, evento["duration_ms"])

    await colecao_grafos.update_one(
        {"aluno_id": aluno_id},
        {"$set": {"grafo": serializar_grafo(grafo)}},
    )
    logger.info(
        "Grafo refinado: aluno_id=%s conceito=%s novo_peso=%s",
        aluno_id, conceito, grafo[aluno_id][conceito]["weight"],
    )


async def processar_mensagem(
    mensagem: aio_pika.abc.AbstractIncomingMessage,
    colecao_telemetria,
    colecao_grafos,
) -> None:
    async with mensagem.process():
        evento = json.loads(mensagem.body.decode("utf-8"))
        # Campo proprio para o TTL, em vez de reaproveitar o `timestamp` do
        # cliente (string ISO, nao tipo Date do Mongo — indice TTL sobre
        # campo string nao expira nada, silenciosamente).
        evento["_retencao_desde"] = datetime.datetime.now(datetime.timezone.utc)
        await colecao_telemetria.insert_one(evento)
        logger.info("Evento persistido: event_id=%s student_id=%s", evento.get("event_id"), evento.get("student_id"))

        await _refinar_grafo_se_aplicavel(evento, colecao_grafos)


async def main() -> None:
    cliente_mongo = AsyncIOMotorClient(SATELLITE_MONGO_URI)
    db = cliente_mongo.get_default_database()
    colecao_telemetria = db[TELEMETRY_COLLECTION]
    colecao_grafos = db[GRAPH_COLLECTION]
    await colecao_telemetria.create_index(
        "_retencao_desde", expireAfterSeconds=RETENCAO_TELEMETRIA_DIAS * 86400,
    )

    conexao = await aio_pika.connect_robust(RABBITMQ_URL)
    async with conexao:
        canal = await conexao.channel()
        await canal.set_qos(prefetch_count=10)

        exchange = await canal.declare_exchange(RABBITMQ_EXCHANGE, ExchangeType.DIRECT, durable=True)
        fila = await canal.declare_queue(QUEUE_NAME, durable=True)
        await fila.bind(exchange, routing_key=QUEUE_NAME)

        logger.info("Worker de ingestão pronto — consumindo fila '%s'", QUEUE_NAME)

        async with fila.iterator() as mensagens:
            async for mensagem in mensagens:
                try:
                    await processar_mensagem(mensagem, colecao_telemetria, colecao_grafos)
                except Exception:
                    logger.exception("Falha ao processar evento de telemetria")


if __name__ == "__main__":
    asyncio.run(main())
