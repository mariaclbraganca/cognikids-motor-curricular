"""Relatório da Rede de Cuidado — Sprint 3 (Graph Mining).

Lê os grafos de todos os alunos na coleção `student_graphs`, monta a rede
aluno-aluno por similaridade de dificuldade (`workers/rede_cuidado.py`) e
imprime centralidade + alunos isolados.

Uso: python scripts/relatorio_rede_cuidado.py [--limiar 0.7]
"""

import argparse
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "workers"))

from knowledge_graph import desserializar_grafo  # noqa: E402
from rede_cuidado import analisar_rede, construir_rede_cuidado, dominio_por_conceito  # noqa: E402

SATELLITE_MONGO_URI = os.environ.get("SATELLITE_MONGO_URI", "mongodb://localhost:27018/cognikids_adapt")


async def carregar_perfis() -> dict[str, dict[str, float]]:
    cliente = AsyncIOMotorClient(SATELLITE_MONGO_URI)
    db = cliente.get_default_database()

    perfis = {}
    async for documento in db["student_graphs"].find({}):
        grafo = desserializar_grafo(documento["grafo"])
        perfis[documento["aluno_id"]] = dominio_por_conceito(grafo, documento["aluno_id"])

    return perfis


async def main(limiar: float) -> None:
    perfis = await carregar_perfis()
    print(f"Alunos com grafo: {len(perfis)}")
    for aluno, dominio in perfis.items():
        print(f"  {aluno}: {dominio if dominio else '(sem conceito avaliado ainda)'}")

    rede = construir_rede_cuidado(perfis, limiar=limiar)
    resultado = analisar_rede(rede)

    print(f"\n=== Rede de Cuidado (limiar de similaridade = {limiar}) ===")
    print(f"Nós: {rede.number_of_nodes()}  |  Arestas: {rede.number_of_edges()}")

    print("\nArestas (similaridade de dificuldade):")
    for a, b, dados in rede.edges(data=True):
        print(f"  {a} -- {b}  similaridade={dados['weight']}")

    print("\nCentralidade de grau (quantos alunos parecidos cada um tem):")
    for aluno, grau in sorted(resultado["centralidade_grau"].items(), key=lambda item: -item[1]):
        print(f"  {aluno}: {grau}")

    print("\nAlunos isolados (perfil de dificuldade sem par parecido na turma):")
    if resultado["alunos_isolados"]:
        for aluno in resultado["alunos_isolados"]:
            print(f"  [ALERTA] {aluno} - candidato a atencao individual")
    else:
        print("  Nenhum")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limiar", type=float, default=0.7)
    args = parser.parse_args()
    asyncio.run(main(args.limiar))
