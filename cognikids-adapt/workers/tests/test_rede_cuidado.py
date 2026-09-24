"""Testes de rede_cuidado.py com cenário verificado à mão (não há notebook
de origem pra essa técnica — é nova neste projeto, ver docstring do módulo)."""

from knowledge_graph import atualizar_aresta_grafo, construir_grafo_cold_start
from rede_cuidado import (
    analisar_rede,
    construir_rede_cuidado,
    dominio_por_conceito,
    similaridade_conceitos,
)


def test_similaridade_com_conceitos_identicos_e_1():
    assert similaridade_conceitos({"X": 0.8}, {"X": 0.8}) == 1.0


def test_similaridade_sem_conceito_em_comum_e_none():
    assert similaridade_conceitos({"X": 0.8}, {"Y": 0.8}) is None


def test_similaridade_usa_so_conceitos_em_comum():
    # X: diff 0.05, Y: diff 0.05 -> media 0.05 -> similaridade 0.95
    # Z existe só em b, não entra na conta
    pesos_a = {"X": 0.9, "Y": 0.8}
    pesos_b = {"X": 0.85, "Y": 0.75, "Z": 0.1}
    assert similaridade_conceitos(pesos_a, pesos_b) == 0.95


def test_dominio_por_conceito_ignora_sinal_de_acessibilidade():
    grafo = construir_grafo_cold_start("aluno-1", {"audio_disponivel": True})
    grafo = atualizar_aresta_grafo(grafo, "aluno-1", "Median", acertou=True, latencia_ms=0)

    dominio = dominio_por_conceito(grafo, "aluno-1")

    assert dominio == {"Median": 1.0}  # sem audio_disponivel, que é sinal de acessibilidade


def test_construir_rede_cuidado_conecta_alunos_similares_e_isola_o_resto():
    perfis = {
        "aluno_a": {"X": 0.9, "Y": 0.8},
        "aluno_b": {"X": 0.85, "Y": 0.75},  # similar a "a" (0.95)
        "aluno_c": {"X": 0.2, "Y": 0.9, "Z": 0.5},  # diferente de a/b (0.6, abaixo do limiar)
        "aluno_d": {"W": 0.5},  # nenhum conceito em comum com ninguém
    }

    grafo = construir_rede_cuidado(perfis, limiar=0.7)

    assert grafo.has_edge("aluno_a", "aluno_b")
    assert grafo["aluno_a"]["aluno_b"]["weight"] == 0.95
    assert not grafo.has_edge("aluno_a", "aluno_c")
    assert not grafo.has_edge("aluno_b", "aluno_c")
    assert grafo.degree("aluno_c") == 0
    assert grafo.degree("aluno_d") == 0


def test_analisar_rede_identifica_isolados_e_centralidade():
    perfis = {
        "aluno_a": {"X": 0.9, "Y": 0.8},
        "aluno_b": {"X": 0.85, "Y": 0.75},
        "aluno_c": {"X": 0.2, "Y": 0.9, "Z": 0.5},
        "aluno_d": {"W": 0.5},
    }
    grafo = construir_rede_cuidado(perfis, limiar=0.7)

    resultado = analisar_rede(grafo)

    assert sorted(resultado["alunos_isolados"]) == ["aluno_c", "aluno_d"]
    assert resultado["centralidade_grau"]["aluno_a"] == 1
    assert resultado["centralidade_grau"]["aluno_c"] == 0
    # Só uma aresta na rede inteira -> nenhum aluno funciona como ponte
    assert all(valor == 0 for valor in resultado["centralidade_intermediacao"].values())
