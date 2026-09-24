from fastapi import APIRouter, Depends, Header, HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients.core_client import alunos_visiveis_do_professor
from app.core.security import professor_autenticado, usuario_autenticado
from app.db.mongo import get_db
from app.schemas.curriculum import CurriculumAdaptAccepted, CurriculumAdaptRequest, CurriculumJobStatus
from app.services import curriculum_service

router = APIRouter(prefix="/v1/curriculum", tags=["curriculum"])


@router.post("/adapt", response_model=CurriculumAdaptAccepted, status_code=202)
async def adaptar_atividade(
    request: CurriculumAdaptRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    usuario: dict = Depends(professor_autenticado),
    authorization: str | None = Header(default=None),
) -> CurriculumAdaptAccepted:
    if request.teacher_id != usuario.get("user_id"):
        raise HTTPException(status_code=403, detail="teacher_id não corresponde ao professor autenticado")

    # Conferir o professor nao basta: antes desta checagem, um professor
    # autenticado podia pedir adaptacao para QUALQUER student_id da base, e o
    # worker_profile buscava os tokens com a conta de servico (admin), que
    # ignora consentimento. Isso furava justamente a garantia da ADR-008.
    permitidos = await alunos_visiveis_do_professor(request.teacher_id, authorization)
    if permitidos is None:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível confirmar a lista de alunos junto ao core — tente novamente",
        )

    nao_autorizados = [aluno_id for aluno_id in request.student_ids if aluno_id not in permitidos]
    if nao_autorizados:
        raise HTTPException(
            status_code=403,
            detail=(
                "Alunos fora da sua turma ou sem consentimento de compartilhamento: "
                + ", ".join(nao_autorizados)
            ),
        )

    job_id, estimativa = await curriculum_service.criar_job(request, db)
    return CurriculumAdaptAccepted(job_id=job_id, status="queued", estimated_seconds=estimativa)


@router.get("/jobs/{job_id}", response_model=CurriculumJobStatus)
async def consultar_job(
    job_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    usuario: dict = Depends(usuario_autenticado),
) -> CurriculumJobStatus:
    documento = await curriculum_service.buscar_job(job_id, db)
    if documento is None:
        raise HTTPException(status_code=404, detail="job_id não encontrado")

    # 404 e nao 403 de proposito: quem nao e dono do job nao deve conseguir
    # nem confirmar que aquele job_id existe.
    if not curriculum_service.pode_ver_job(documento, usuario):
        raise HTTPException(status_code=404, detail="job_id não encontrado")

    return curriculum_service.montar_status(documento)


@router.put("/jobs/{job_id}/adaptations/{adaptation_id}/approve", response_model=CurriculumJobStatus)
async def aprovar_adaptacao(
    job_id: str,
    adaptation_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    usuario: dict = Depends(professor_autenticado),
) -> CurriculumJobStatus:
    """Professor aprova uma versao adaptada especifica antes dela chegar ao aluno.

    O principio "o professor revisa e aprova cada versao" nao tinha nenhum
    registro em codigo ate agora — qualquer adaptacao gerada ficava
    implicitamente liberada.
    """
    documento = await curriculum_service.buscar_job(job_id, db)
    if documento is None:
        raise HTTPException(status_code=404, detail="job_id não encontrado")

    # Mesma logica de consultar_job: quem nao e dono nao deve nem confirmar
    # que o job existe. Diferente de pode_ver_job, o aluno citado no job NAO
    # pode aprovar — so o professor dono.
    if not curriculum_service.eh_dono_do_job(documento, usuario):
        raise HTTPException(status_code=404, detail="job_id não encontrado")

    resultado = await curriculum_service.aprovar_adaptacao(
        job_id, adaptation_id, usuario.get("user_id"), db
    )
    if resultado == "nao_encontrada":
        raise HTTPException(status_code=404, detail="adaptation_id não encontrado neste job")

    documento_atualizado = await curriculum_service.buscar_job(job_id, db)
    return curriculum_service.montar_status(documento_atualizado)
