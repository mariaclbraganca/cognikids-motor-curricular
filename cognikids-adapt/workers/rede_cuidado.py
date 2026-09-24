"""Rede de Cuidado — grafo aluno-aluno por similaridade de dificuldade.

Reaproveita os grafos individuais já construídos por `knowledge_graph.py`
(coleção `student_graphs`): dois alunos ficam conectados quando o padrão de
domínio deles sobre os mesmos conceitos é parecido. Mesma filosofia
determinística/explicável do resto do projeto — sem modelo treinado, sem LLM
(consistente com a ADR-006 e com a abordagem de correlação de desempenho do
Núcleo 2, só que aplicada entre alunos em vez de entre conceitos).

Diferente da correlação de Pearson usada no Núcleo 2 (que precisava de
dezenas de alunos com o mesmo par de conceitos pra ser confiável — ver
`min_periods=15` no notebook), aqui a base é pequena e esparsa no início do
projeto: cada aluno tem só os conceitos com que já interagiu, muitas vezes
1 ou 2. Por isso a métrica de similaridade usada é a distância média absoluta
sobre os conceitos em comum (funciona com 1 conceito só, não exige volume de
dado) — o preço é ser uma métrica mais simples, não uma correlação estatística.

Uso pedagógico: centralidade alta = padrão de dificuldade comum na turma
(candidato a intervenção em grupo); nó isolado = aluno com perfil de
dificuldade sem par parecido na turma (candidato a atenção individual).
"""

import networkx as nx

LIMIAR_SIMILARIDADE_PADRAO = 0.7


def dominio_por_conceito(grafo: nx.Graph, aluno_id: str) -> dict[str, float]:
    """Pesos de domínio do aluno, só sobre nós tipo='conceito'.

    Filtra os nós de sinal de acessibilidade (cold start, ver
    `knowledge_graph.py`) porque eles não representam desempenho real —
    todos nascem com peso neutro 0.5, comparar isso entre alunos não diz
    nada sobre dificuldade compartilhada.
    """
    if aluno_id not in grafo:
        return {}
    return {
        vizinho: grafo[aluno_id][vizinho]["weight"]
        for vizinho in grafo.neighbors(aluno_id)
        if grafo.nodes[vizinho].get("tipo") == "conceito"
    }


def similaridade_conceitos(pesos_a: dict[str, float], pesos_b: dict[str, float]) -> float | None:
    """1 - distância média absoluta sobre os conceitos em comum.

    None quando não há nenhum conceito em comum — os dois alunos não são
    comparáveis ainda, não é o mesmo que "totalmente diferentes".
    """
    conceitos_comuns = set(pesos_a) & set(pesos_b)
    if not conceitos_comuns:
        return None

    distancia_media = sum(abs(pesos_a[c] - pesos_b[c]) for c in conceitos_comuns) / len(conceitos_comuns)
    return round(1 - distancia_media, 3)


def construir_rede_cuidado(
    perfis: dict[str, dict[str, float]],
    limiar: float = LIMIAR_SIMILARIDADE_PADRAO,
) -> nx.Graph:
    """Grafo aluno-aluno. Aresta só quando similaridade >= limiar.

    `perfis` = {aluno_id: {conceito: peso}}, tipicamente a saída de
    `dominio_por_conceito()` para cada aluno de uma turma.
    """
    grafo = nx.Graph()
    grafo.add_nodes_from(perfis.keys())

    alunos = list(perfis.keys())
    for i, aluno_a in enumerate(alunos):
        for aluno_b in alunos[i + 1:]:
            similaridade = similaridade_conceitos(perfis[aluno_a], perfis[aluno_b])
            if similaridade is not None and similaridade >= limiar:
                grafo.add_edge(aluno_a, aluno_b, weight=similaridade)

    return grafo


def analisar_rede(grafo: nx.Graph) -> dict:
    """Centralidade + alunos isolados, para o relatório/dashboard."""
    return {
        "centralidade_grau": dict(grafo.degree()),
        "centralidade_intermediacao": nx.betweenness_centrality(grafo, weight="weight"),
        "alunos_isolados": [aluno for aluno in grafo.nodes if grafo.degree(aluno) == 0],
    }
