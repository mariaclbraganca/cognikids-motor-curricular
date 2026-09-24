"""Cascata de revogacao de consentimento — lado satelite (ADR-008/ADR-010).

DELETE /v1/students/{aluno_id}/behavioral-data so pode ser chamado pelo
core (token de servico), nunca por um JWT de usuario humano — mesmo que
seja um professor ou admin legitimo autenticado.
"""

from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.mongo import get_db
from app.main import app


class _ColecaoFalsa:
    def __init__(self, deleted_count=0):
        self.deleted_count = deleted_count
        self.chamadas = []

    async def delete_many(self, filtro):
        self.chamadas.append(filtro)
        return SimpleNamespace(deleted_count=self.deleted_count)


class _DbFalso:
    def __init__(self, grafos=0, telemetria=0):
        self.colecoes = {
            "student_graphs": _ColecaoFalsa(grafos),
            "telemetry_events": _ColecaoFalsa(telemetria),
        }

    def __getitem__(self, nome):
        return self.colecoes[nome]


@pytest.fixture
def db_falso():
    return _DbFalso(grafos=1, telemetria=7)


SEGREDO_TESTE = "segredo-compartilhado-de-teste-1234567890"


@pytest.fixture
def cliente(db_falso, monkeypatch):
    # settings.core_jwt_secret vem vazio por padrao (config.py) — precisa de
    # um segredo real para o jwt.encode/decode ter algo pra assinar/validar.
    monkeypatch.setattr(settings, "core_jwt_secret", SEGREDO_TESTE)
    app.dependency_overrides[get_db] = lambda: db_falso
    yield TestClient(app)
    app.dependency_overrides.clear()


def _token_servico():
    return jwt.encode({"servico": "core"}, SEGREDO_TESTE, algorithm="HS256")


def _token_humano(role="professor"):
    return jwt.encode({"user_id": "prof-1", "role": role}, SEGREDO_TESTE, algorithm="HS256")


def test_core_purga_dados_comportamentais_do_aluno(cliente, db_falso):
    resposta = cliente.delete(
        "/v1/students/aluno-123/behavioral-data",
        headers={"Authorization": f"Bearer {_token_servico()}"},
    )

    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()["data"]
    assert dados["aluno_id"] == "aluno-123"
    assert dados["student_graphs_removidos"] == 1
    assert dados["telemetry_events_removidos"] == 7


def test_filtra_cada_colecao_pelo_campo_certo(cliente, db_falso):
    """student_graphs usa 'aluno_id'; telemetry_events usa 'student_id' —
    formatos diferentes por desenho (worker_profile.py vs schemas/telemetry.py),
    nao inconsistencia. Se alguem 'corrigir' isso sem saber, a cascata para
    de encontrar o dado a apagar, silenciosamente.
    """
    cliente.delete(
        "/v1/students/aluno-123/behavioral-data",
        headers={"Authorization": f"Bearer {_token_servico()}"},
    )

    assert db_falso.colecoes["student_graphs"].chamadas == [{"aluno_id": "aluno-123"}]
    assert db_falso.colecoes["telemetry_events"].chamadas == [{"student_id": "aluno-123"}]


def test_jwt_de_professor_nao_purga_dados_de_ninguem(cliente, db_falso):
    """Nem um professor autenticado de verdade pode chamar esta rota —
    so o token de servico que o core emite para esta finalidade especifica.
    """
    resposta = cliente.delete(
        "/v1/students/aluno-123/behavioral-data",
        headers={"Authorization": f"Bearer {_token_humano('professor')}"},
    )

    assert resposta.status_code == 403, (
        "REGRESSAO CRITICA: JWT de usuario humano purgou dados comportamentais"
    )
    assert db_falso.colecoes["student_graphs"].chamadas == []
    assert db_falso.colecoes["telemetry_events"].chamadas == []


def test_sem_token_e_recusado(cliente, db_falso):
    resposta = cliente.delete("/v1/students/aluno-123/behavioral-data")
    assert resposta.status_code == 401
    assert db_falso.colecoes["student_graphs"].chamadas == []
