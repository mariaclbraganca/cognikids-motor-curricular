import pytest
from pydantic import ValidationError

from app.schemas.curriculum import Adaptation, CurriculumAdaptRequest, CurriculumJobStatus

VALID_REQUEST = {
    "teacher_id": "professor-123",
    "title": "A fotossíntese",
    "subject": "Ciências",
    "original_content": "Explique o processo de fotossíntese nas plantas.",
    "student_ids": ["aluno-1", "aluno-2"],
    "habilidade_bncc": "EF03CI04",
}


def test_request_valida_e_aceita():
    request = CurriculumAdaptRequest(**VALID_REQUEST)
    assert request.teacher_id == "professor-123"
    assert len(request.student_ids) == 2


@pytest.mark.parametrize(
    "campo_removido", ["teacher_id", "title", "original_content", "student_ids", "habilidade_bncc"]
)
def test_request_sem_campo_obrigatorio_e_rejeitada(campo_removido):
    dados = {k: v for k, v in VALID_REQUEST.items() if k != campo_removido}
    with pytest.raises(ValidationError):
        CurriculumAdaptRequest(**dados)


def test_request_com_student_ids_nao_lista_e_rejeitada():
    dados = {**VALID_REQUEST, "student_ids": "aluno-1"}
    with pytest.raises(ValidationError):
        CurriculumAdaptRequest(**dados)


def test_job_status_aceita_lista_de_adaptacoes_vazia_por_padrao():
    job = CurriculumJobStatus(job_id="abc", status="queued", habilidade_bncc="EF03CI04")
    assert job.adaptations == []


def test_adaptation_exige_todos_os_campos_do_contrato():
    adaptacao = Adaptation(
        adaptation_id="adapt-1",
        student_id="aluno-1",
        adapted_content="Texto adaptado",
        format_applied=["passo_a_passo", "audio"],
        xai_explanation="Explicação",
        profile_tokens_used={"audio_disponivel": True},
        habilidade_bncc="EF03CI04",
    )
    assert adaptacao.format_applied == ["passo_a_passo", "audio"]


def test_adaptation_nasce_nao_aprovada_por_padrao():
    """O professor ainda nao revisou nada — approved so vira True por acao dele."""
    adaptacao = Adaptation(
        adaptation_id="adapt-1",
        student_id="aluno-1",
        adapted_content="Texto adaptado",
        format_applied=["passo_a_passo"],
        xai_explanation="Explicação",
        profile_tokens_used={},
        habilidade_bncc="EF03CI04",
    )
    assert adaptacao.approved is False
    assert adaptacao.approved_by is None
    assert adaptacao.approved_at is None


class TestPreservaHabilidade:
    """Igualdade de string entre a habilidade original e a da versao adaptada."""

    def test_mesma_habilidade_preserva(self):
        from app.services.curriculum_service import preserva_habilidade

        assert preserva_habilidade("EF03CI04", "EF03CI04") is True

    def test_habilidade_diferente_nao_preserva(self):
        from app.services.curriculum_service import preserva_habilidade

        assert preserva_habilidade("EF03CI04", "EF03CI05") is False

    def test_normaliza_espaco_e_caixa(self):
        from app.services.curriculum_service import preserva_habilidade

        assert preserva_habilidade("EF03CI04", " ef03ci04 ") is True
