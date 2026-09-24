import uuid
from datetime import datetime, timezone
from typing import Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.clients import rabbitmq
from app.schemas.curriculum import CurriculumAdaptRequest, CurriculumJobStatus

COLLECTION = "curriculum_jobs"


def _estimar_segundos(quantidade_alunos: int) -> int:
    # Heurística simples: tempo base de fila + tempo proporcional por aluno
    # (cada aluno gera uma chamada de análise + adaptação em paralelo, ver CLAUDE.md seção 10)
    return 5 + 2 * quantidade_alunos


async def criar_job(request: CurriculumAdaptRequest, db: AsyncIOMotorDatabase) -> tuple[str, int]:
    job_id = str(uuid.uuid4())
    estimativa = _estimar_segundos(len(request.student_ids))

    await db[COLLECTION].insert_one({
        "job_id": job_id,
        "status": "queued",
        "teacher_id": request.teacher_id,
        "title": request.title,
        "subject": request.subject,
        "original_content": request.original_content,
        "student_ids": request.student_ids,
        "habilidade_bncc": request.habilidade_bncc,
        "adaptations": [],
        "created_at": datetime.now(timezone.utc),
    })

    await rabbitmq.publish("analysis", {
        "job_id": job_id,
        "teacher_id": request.teacher_id,
        "title": request.title,
        "subject": request.subject,
        "original_content": request.original_content,
        "student_ids": request.student_ids,
        "habilidade_bncc": request.habilidade_bncc,
    })

    return job_id, estimativa


async def buscar_job(job_id: str, db: AsyncIOMotorDatabase) -> dict | None:
    """Documento bruto do job — inclui teacher_id/student_ids, que o schema
    de resposta nao expoe mas a checagem de propriedade precisa.
    """
    return await db[COLLECTION].find_one({"job_id": job_id}, {"_id": 0})


def eh_dono_do_job(documento: dict, usuario: dict) -> bool:
    """So o professor que criou o job pode aprovar uma versao adaptada.

    Diferente de pode_ver_job: o aluno citado no job consegue LER o proprio
    job, mas aprovar e' decisao do professor — o aluno nao se autoaprova.
    """
    return documento.get("teacher_id") == usuario.get("user_id")


async def aprovar_adaptacao(
    job_id: str, adaptation_id: str, professor_id: str, db: AsyncIOMotorDatabase
) -> Literal["aprovada", "ja_aprovada", "nao_encontrada"]:
    """Registra a aprovacao do professor sobre uma versao adaptada especifica.

    Idempotente por desenho (mesmo padrao de approve_creation no core,
    gallery_model.py): aprovar duas vezes nao sobrescreve approved_by/
    approved_at da primeira aprovacao, so confirma que ja estava aprovada.
    """
    agora = datetime.now(timezone.utc)
    resultado = await db[COLLECTION].update_one(
        {"job_id": job_id, "adaptations.adaptation_id": adaptation_id},
        {
            "$set": {
                "adaptations.$[elem].approved": True,
                "adaptations.$[elem].approved_by": professor_id,
                "adaptations.$[elem].approved_at": agora,
            }
        },
        array_filters=[{"elem.adaptation_id": adaptation_id, "elem.approved": {"$ne": True}}],
    )

    if resultado.matched_count == 0:
        return "nao_encontrada"
    if resultado.modified_count == 0:
        return "ja_aprovada"
    return "aprovada"


def pode_ver_job(documento: dict, usuario: dict) -> bool:
    """So o professor que criou o job e os alunos citados nele podem le-lo.

    Antes desta checagem, GET /v1/curriculum/jobs/{job_id} exigia apenas um
    JWT valido de qualquer perfil: quem obtivesse um job_id (log, URL, app)
    lia `original_content`, a lista de alunos e — quando o worker de
    adaptacao existir — `profile_tokens_used`, que e o perfil funcional da
    crianca.

    Responsavel ainda nao entra aqui: liberar o pai exige perguntar ao core
    se aquele aluno e filho dele, e negar por padrao e' o lado seguro
    enquanto essa chamada nao existe.
    """
    user_id = usuario.get("user_id")
    if documento.get("teacher_id") == user_id:
        return True
    return user_id in (documento.get("student_ids") or [])


def montar_status(documento: dict) -> CurriculumJobStatus:
    return CurriculumJobStatus(**documento)


def preserva_habilidade(esperada: str, obtida: str) -> bool:
    """Verifica se uma versao adaptada preserva a habilidade BNCC original.

    Igualdade de string, nao interpretacao semantica — e' deliberadamente
    ingenuo: o objetivo e' dar um sinal automatico e auditavel de que a
    adaptacao pode ter mudado o objetivo pedagogico (viraria modificacao,
    nao acomodacao), nao substituir o julgamento do professor. Normaliza
    espacos e caixa porque "EF03LP01" e " ef03lp01 " devem contar como a
    mesma habilidade.
    """
    return esperada.strip().casefold() == obtida.strip().casefold()
