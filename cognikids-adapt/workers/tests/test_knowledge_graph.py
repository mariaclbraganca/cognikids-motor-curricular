"""Teste de regressão: a porta de knowledge_graph.py precisa reproduzir os
mesmos resultados validados no notebook Núcleo 2 (peso 0.25 -> 0.555 após 3
acertos seguidos, ver ADR relacionada à seção 5.1 do CLAUDE.md).
"""

from knowledge_graph import (
    atualizar_aresta_grafo,
    construir_grafo_cold_start,
    desserializar_grafo,
    resumo_dominio,
    serializar_grafo,
)


def test_cold_start_usa_so_tokens_ativos_com_peso_neutro():
    grafo = construir_grafo_cold_start(
        "aluno_14",
        {"audio_disponivel": True, "fonte_ampliada": True, "instrucao_uma_por_vez": False},
    )
    assert resumo_dominio(grafo, "aluno_14") == {"audio_disponivel": 0.5, "fonte_ampliada": 0.5}


def test_cold_start_sem_tokens_gera_grafo_so_com_o_aluno():
    grafo = construir_grafo_cold_start("aluno_novo", {})
    assert list(grafo.nodes) == ["aluno_novo"]
    assert resumo_dominio(grafo, "aluno_novo") == {}


def test_atualizacao_incremental_reproduz_o_resultado_do_notebook():
    """Cenário exato do notebook: Median parte de 0.25, 3 acertos seguidos
    com latência de 15s levam o peso a 0.555 (média móvel 0.8/0.2)."""
    grafo = construir_grafo_cold_start("aluno_14", {})
    grafo.add_edge("aluno_14", "Median", weight=0.25, n_interacoes=4)

    for _ in range(3):
        grafo = atualizar_aresta_grafo(grafo, "aluno_14", "Median", acertou=True, latencia_ms=15000)

    assert grafo["aluno_14"]["Median"]["weight"] == 0.555


def test_atualizacao_incremental_cria_aresta_nova_quando_conceito_e_inedito():
    grafo = construir_grafo_cold_start("aluno_novo", {})
    grafo = atualizar_aresta_grafo(grafo, "aluno_novo", "Range", acertou=True, latencia_ms=0)

    assert grafo.has_edge("aluno_novo", "Range")
    assert grafo["aluno_novo"]["Range"]["n_interacoes"] == 1


def test_serializacao_sobrevive_ao_round_trip_mongo():
    grafo = construir_grafo_cold_start("aluno_14", {"audio_disponivel": True})
    grafo = atualizar_aresta_grafo(grafo, "aluno_14", "Median", acertou=False, latencia_ms=60000)

    reconstruido = desserializar_grafo(serializar_grafo(grafo))

    assert resumo_dominio(reconstruido, "aluno_14") == resumo_dominio(grafo, "aluno_14")
