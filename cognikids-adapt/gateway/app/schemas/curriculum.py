from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class CurriculumAdaptRequest(BaseModel):
    teacher_id: str
    title: str
    subject: str
    original_content: str
    student_ids: list[str]
    # Codigo da habilidade da BNCC que a atividade original endereca (ex.:
    # "EF03LP01"). Sem isso, nao ha como verificar depois se a versao
    # adaptada preserva a habilidade ou se virou modificacao de objetivo —
    # a distincao que sustenta o principio "adaptar formato, nunca conteudo".
    habilidade_bncc: str


class CurriculumAdaptAccepted(BaseModel):
    job_id: str
    status: Literal["queued"]
    estimated_seconds: int


class Adaptation(BaseModel):
    adaptation_id: str
    student_id: str
    adapted_content: str
    format_applied: list[str]
    xai_explanation: str
    profile_tokens_used: dict[str, Any]
    # Habilidade BNCC que esta versao adaptada afirma preservar. Deve ser
    # comparado contra CurriculumJobStatus.habilidade_bncc via
    # curriculum_service.preserva_habilidade — igualdade de string simples,
    # nao interpretacao semantica.
    habilidade_bncc: str
    # O principio "o professor revisa e aprova cada versao" (CLAUDE.md) nao
    # tinha nenhum campo para registrar isso — a adaptacao ficava disponivel
    # sem que nada no schema distinguisse revisada de nao revisada.
    approved: bool = False
    approved_by: str | None = None
    approved_at: datetime | None = None


class CurriculumJobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    habilidade_bncc: str
    adaptations: list[Adaptation] = []
