from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

# Nao ha finalidade legitima para manter conteudo de atividade e tokens de
# acessibilidade usados num job de adaptacao indefinidamente — auditoria de
# LGPD encontrou retencao indefinida em toda colecao sensivel do satelite.
RETENCAO_CURRICULUM_JOBS_DIAS = 180


def connect() -> None:
    global _client, _db

    _client = AsyncIOMotorClient(settings.satellite_mongo_uri)
    _db = _client.get_default_database()


async def ensure_indexes() -> None:
    """Cria os indices de retencao (TTL). Chamado uma vez no startup —
    create_index e idempotente, nao recria se ja existir com os mesmos
    parametros.
    """
    db = get_db()
    await db["curriculum_jobs"].create_index(
        "created_at", expireAfterSeconds=RETENCAO_CURRICULUM_JOBS_DIAS * 86400,
    )


def close() -> None:
    if _client is not None:
        _client.close()


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB não conectado — chame connect() no startup da aplicação")
    return _db
