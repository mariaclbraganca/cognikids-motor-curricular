"""
Cascata de revogacao de consentimento — lado satelite (ADR-008/ADR-010).

Chamado pelo core (Utils/satellite_client.py) quando um responsavel revoga
coleta_biometrica. O core ja apaga registros_iot/alerts no proprio banco;
este modulo apaga o equivalente do lado satelite, que deriva do mesmo dado
comportamental dois artefatos proprios: o grafo de conhecimento
(student_graphs, worker_profile.py) e a telemetria bruta (telemetry_events,
worker_ingestion.py). Antes desta correcao, revogar no core deixava rastro
comportamental equivalente vivo no satelite indefinidamente.

Escopo deliberadamente restrito a estas duas colecoes: curriculum_jobs nao
entra aqui porque não e' derivado especificamente de coleta_biometrica (e'
conteudo pedagogico do professor, ligado a compartilhar_escola/uso_app, um
consentimento diferente) — apagar isso e' uma decisao de produto separada,
nao coberta por esta cascata.
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

STUDENT_GRAPHS_COLLECTION = "student_graphs"
TELEMETRY_COLLECTION = "telemetry_events"


async def purgar_dados_comportamentais(aluno_id: str, db: AsyncIOMotorDatabase) -> dict:
    """Remove o grafo de conhecimento e a telemetria bruta de um aluno.

    Os dois campos de identificacao sao diferentes de proposito: worker_profile.py
    grava student_graphs com 'aluno_id', e o schema TelemetryEvent usa
    'student_id' — nao e' inconsistencia a corrigir aqui, e' o formato real
    de cada colecao.
    """
    resultado_grafo = await db[STUDENT_GRAPHS_COLLECTION].delete_many({"aluno_id": aluno_id})
    resultado_telemetria = await db[TELEMETRY_COLLECTION].delete_many({"student_id": aluno_id})

    return {
        "aluno_id": aluno_id,
        "student_graphs_removidos": resultado_grafo.deleted_count,
        "telemetry_events_removidos": resultado_telemetria.deleted_count,
    }
