"""Grafo de Conhecimento por aluno — sem LLM, determinístico (ver CLAUDE.md
seção 5.1). Portado de `cognikids-adapt/notebooks/nucleo2_grafo_conhecimento.ipynb`.

Nós = conceitos cognitivos (formato de processamento associado); arestas =
domínio do aluno sobre o conceito, ponderado por sinais comportamentais.

Duas fases:
1. **Cold start** (implementado aqui) — o grafo nasce com o sinal grosseiro
   dos tokens de acessibilidade configurados no core. Cada token ativo vira
   um nó com peso neutro (0.5), sem ainda ter dado de desempenho.
2. **Refinamento por TelemetryEvent** (NÃO implementado ainda) — precisa de
   um campo de acerto e de conceito no contrato de TelemetryEvent
   (`gateway/app/schemas/telemetry.py`), que hoje não existe (só
   `activity_id` + `metadata` livre). `atualizar_aresta_grafo()` abaixo já
   está pronta para consumir esse sinal assim que o contrato existir — quem
   ainda falta escrever é o consumidor (worker_ingestion.py ou um worker
   novo) que lê o TelemetryEvent e chama essa função.
"""

import networkx as nx

CAP_LATENCIA_MS = 60_000
PESO_COLD_START = 0.5


def construir_grafo_cold_start(aluno_id: str, tokens: dict) -> nx.Graph:
    """Grafo inicial a partir dos tokens de acessibilidade do core.

    Sinal grosseiro por design (seção 5.1 do CLAUDE.md): cada token ativo
    vira um nó com peso neutro — ainda não há dado de desempenho real do
    aluno, só a configuração que os pais fizeram no core.
    """
    grafo = nx.Graph()
    grafo.add_node(aluno_id, tipo="aluno")

    for token, valor in (tokens or {}).items():
        if not valor:
            continue
        grafo.add_node(token, tipo="sinal_acessibilidade")
        grafo.add_edge(aluno_id, token, weight=PESO_COLD_START, n_interacoes=0)

    return grafo


def atualizar_aresta_grafo(grafo: nx.Graph, aluno_id: str, conceito: str, acertou: bool, latencia_ms: float) -> nx.Graph:
    """Atualização incremental por evento (ver Fase 6 do notebook Núcleo 2).

    Média móvel 0.8 histórico / 0.2 evento novo — evita que um único evento
    mude o grafo de uma vez, domínio é construído ao longo de várias
    interações, não decidido numa tentativa isolada.
    """
    velocidade_normalizada = 1 - min(latencia_ms, CAP_LATENCIA_MS) / CAP_LATENCIA_MS
    peso_evento = (int(acertou) + velocidade_normalizada) / 2

    if grafo.has_edge(aluno_id, conceito):
        peso_atual = grafo[aluno_id][conceito]["weight"]
        novo_peso = round(0.8 * peso_atual + 0.2 * peso_evento, 3)
        grafo[aluno_id][conceito]["weight"] = novo_peso
        grafo[aluno_id][conceito]["n_interacoes"] += 1
    else:
        grafo.add_node(conceito, tipo="conceito")
        grafo.add_edge(aluno_id, conceito, weight=round(peso_evento, 3), n_interacoes=1)

    return grafo


def serializar_grafo(grafo: nx.Graph) -> dict:
    return nx.node_link_data(grafo, edges="edges")


def desserializar_grafo(dados: dict) -> nx.Graph:
    return nx.node_link_graph(dados, edges="edges")


def resumo_dominio(grafo: nx.Graph, aluno_id: str) -> dict[str, float]:
    """{conceito: peso} para o worker de adaptação decidir o que reforçar.

    Não inclui o próprio nó do aluno, só os conceitos/sinais conectados a ele.
    """
    if aluno_id not in grafo:
        return {}
    return {
        vizinho: grafo[aluno_id][vizinho]["weight"]
        for vizinho in grafo.neighbors(aluno_id)
    }
