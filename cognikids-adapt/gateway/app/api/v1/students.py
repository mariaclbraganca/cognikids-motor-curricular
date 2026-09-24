"""Rotas de efeito administrativo entre servicos — nao para uso humano.

Hoje so a cascata de revogacao de consentimento (ADR-008/ADR-010): o core
chama isto quando um responsavel revoga coleta_biometrica.
"""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import servico_core_autenticado
from app.db.mongo import get_db
from app.services import student_data_service

router = APIRouter(prefix="/v1/students", tags=["students"])


@router.delete("/{aluno_id}/behavioral-data")
async def purgar_dados_comportamentais(
    aluno_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    _servico: dict = Depends(servico_core_autenticado),
) -> dict:
    """Remove student_graphs e telemetry_events do aluno.

    Só o core pode chamar (servico_core_autenticado) — não é uma rota que
    um professor ou responsável deveria acionar diretamente.
    """
    resultado = await student_data_service.purgar_dados_comportamentais(aluno_id, db)
    return {"status": "sucesso", "data": resultado}
