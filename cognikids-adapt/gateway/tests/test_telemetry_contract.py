import pytest
from pydantic import ValidationError

from app.schemas.telemetry import TelemetryEvent

VALID_EVENT = {
    "event_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "student_id": "aluno-123",
    "activity_id": "atividade-456",
    "session_id": "sessao-789",
    "event_type": "step_completed",
    "step_number": 2,
    "duration_ms": 4200,
    "timestamp": "2026-08-13T12:00:00Z",
    "metadata": {"formato": "audio"},
}


def test_evento_valido_e_aceito():
    evento = TelemetryEvent(**VALID_EVENT)
    assert evento.event_type == "step_completed"
    assert evento.duration_ms == 4200


def test_evento_sem_metadata_usa_default():
    dados = {k: v for k, v in VALID_EVENT.items() if k != "metadata"}
    evento = TelemetryEvent(**dados)
    assert evento.metadata == {}


@pytest.mark.parametrize("campo_removido", ["event_id", "student_id", "duration_ms", "timestamp"])
def test_evento_sem_campo_obrigatorio_e_rejeitado(campo_removido):
    dados = {k: v for k, v in VALID_EVENT.items() if k != campo_removido}
    with pytest.raises(ValidationError):
        TelemetryEvent(**dados)


def test_evento_com_event_type_invalido_e_rejeitado():
    dados = {**VALID_EVENT, "event_type": "voou_da_cadeira"}
    with pytest.raises(ValidationError):
        TelemetryEvent(**dados)


def test_evento_com_duration_ms_nao_numerico_e_rejeitado():
    dados = {**VALID_EVENT, "duration_ms": "muito_tempo"}
    with pytest.raises(ValidationError):
        TelemetryEvent(**dados)


def test_evento_sem_concept_e_correct_usa_default_none():
    evento = TelemetryEvent(**VALID_EVENT)
    assert evento.concept is None
    assert evento.correct is None


def test_evento_com_concept_e_correct_e_aceito():
    dados = {**VALID_EVENT, "concept": "sequência_auditiva", "correct": True}
    evento = TelemetryEvent(**dados)
    assert evento.concept == "sequência_auditiva"
    assert evento.correct is True


def test_evento_com_correct_nao_booleano_e_rejeitado():
    dados = {**VALID_EVENT, "correct": "sim"}
    with pytest.raises(ValidationError):
        TelemetryEvent(**dados)
