"""Testa _refinar_grafo_se_aplicavel sem precisar de MongoDB real — uma
coleção falsa em memória imita a interface async do motor (find_one/update_one)
o suficiente para o teste."""

import pytest

from knowledge_graph import construir_grafo_cold_start, serializar_grafo
from worker_ingestion import _refinar_grafo_se_aplicavel


class ColecaoGrafosFalsa:
    def __init__(self, documentos: dict[str, dict]):
        self._documentos = documentos

    async def find_one(self, filtro):
        return self._documentos.get(filtro["aluno_id"])

    async def update_one(self, filtro, atualizacao):
        aluno_id = filtro["aluno_id"]
        self._documentos.setdefault(aluno_id, {"aluno_id": aluno_id})
        self._documentos[aluno_id]["grafo"] = atualizacao["$set"]["grafo"]


def _evento_base(**overrides):
    evento = {
        "event_id": "evt-1",
        "student_id": "aluno-1",
        "activity_id": "atividade-1",
        "session_id": "sessao-1",
        "event_type": "step_completed",
        "step_number": 1,
        "concept": "sequência_auditiva",
        "correct": True,
        "duration_ms": 15000,
        "timestamp": "2026-08-14T12:00:00Z",
        "metadata": {},
    }
    evento.update(overrides)
    return evento


@pytest.mark.asyncio
async def test_refina_grafo_quando_ha_concept_e_correct_e_grafo_existente():
    grafo_inicial = construir_grafo_cold_start("aluno-1", {})
    grafo_inicial.add_edge("aluno-1", "sequência_auditiva", weight=0.25, n_interacoes=4)
    colecao = ColecaoGrafosFalsa({"aluno-1": {"aluno_id": "aluno-1", "grafo": serializar_grafo(grafo_inicial)}})

    for _ in range(3):
        await _refinar_grafo_se_aplicavel(_evento_base(), colecao)

    grafo_final_dados = colecao._documentos["aluno-1"]["grafo"]
    aresta = next(e for e in grafo_final_dados["edges"] if "sequência_auditiva" in (e["source"], e["target"]))
    assert aresta["weight"] == 0.555  # mesmo resultado validado no notebook (ver test_knowledge_graph.py)


@pytest.mark.asyncio
async def test_ignora_evento_sem_concept():
    colecao = ColecaoGrafosFalsa({})
    await _refinar_grafo_se_aplicavel(_evento_base(concept=None), colecao)
    assert colecao._documentos == {}


@pytest.mark.asyncio
async def test_ignora_evento_sem_correct():
    colecao = ColecaoGrafosFalsa({})
    await _refinar_grafo_se_aplicavel(_evento_base(correct=None), colecao)
    assert colecao._documentos == {}


@pytest.mark.asyncio
async def test_ignora_evento_que_nao_e_step_completed():
    colecao = ColecaoGrafosFalsa({})
    await _refinar_grafo_se_aplicavel(_evento_base(event_type="hint_requested"), colecao)
    assert colecao._documentos == {}


@pytest.mark.asyncio
async def test_ignora_quando_aluno_nao_tem_grafo_ainda_cold_start_nao_rodou():
    colecao = ColecaoGrafosFalsa({})
    await _refinar_grafo_se_aplicavel(_evento_base(), colecao)
    assert colecao._documentos == {}
