"""Experimento: centralizado vs. federado (Sprint 3 — Computação Distribuída).

Compara duas formas de treinar o mesmo classificador de risco de crise
(SGDClassifier sobre BPM/GSR/movimento) em 4 escolas simuladas com
perfis diferentes (não-IID, ver `fl_dataset.py`):

1. Centralizado: todo o dado de todas as escolas é juntado num só lugar
   antes de treinar — a linha de base de "melhor caso possível", mas que
   nenhuma escola aceitaria na prática (dado sensível de criança saindo do
   prédio, ver ADR-003/004 no CLAUDE.md).
2. Federado (FedAvg via Flower): cada escola treina localmente, só os
   parâmetros do modelo (`coef_`/`intercept_`) trafegam e são agregados —
   o dado bruto nunca sai da escola.

A agregação usa `flwr.server.strategy.aggregate.aggregate()` de verdade (a
mesma função que o Flower usa por baixo dos panos na estratégia FedAvg) —
o loop de rounds é conduzido manualmente aqui em vez de usar o simulador
baseado em Ray do Flower, que tem suporte instável no Windows.

Uso: python experimento_fedavg.py [--rounds 10]
"""

import argparse

import numpy as np
from flwr.server.strategy.aggregate import aggregate
from sklearn.linear_model import SGDClassifier

from fl_dataset import gerar_dados_escola, gerar_particoes
from fl_model import CLASSES, ClienteEscola, criar_modelo, definir_parametros, obter_parametros


def montar_conjunto_teste_global(n_por_escola: int = 150) -> tuple[np.ndarray, np.ndarray]:
    """Um conjunto de teste combinando as 4 escolas — mesma distribuição
    real (mistura de todos os perfis), usado pra avaliar os dois modelos
    de forma comparável. Seeds diferentes das usadas no treino."""
    Xs, ys = [], []
    for i, escola in enumerate(["escola_a", "escola_b", "escola_c", "escola_d"]):
        X, y = gerar_dados_escola(escola, n_por_escola, 9000 + i)
        Xs.append(X)
        ys.append(y)
    return np.concatenate(Xs), np.concatenate(ys)


def treinar_centralizado(particoes: dict, epocas: int) -> SGDClassifier:
    """Mesmo otimizador (SGD) e mesmo número total de épocas que o federado
    roda (rounds * épocas locais) — a única diferença isolada é acesso
    centralizado ao dado de uma vez vs. treino distribuído + agregação."""
    X_todo = np.concatenate([X for X, _ in particoes.values()])
    y_todo = np.concatenate([y for _, y in particoes.values()])

    modelo = criar_modelo()
    for _ in range(epocas):
        modelo.partial_fit(X_todo, y_todo, classes=CLASSES)
    return modelo


def treinar_federado(particoes: dict, rounds: int) -> SGDClassifier:
    clientes = {escola: ClienteEscola(X, y) for escola, (X, y) in particoes.items()}

    modelo_global = criar_modelo()
    parametros_globais = obter_parametros(modelo_global)

    for rodada in range(1, rounds + 1):
        resultados_fit = []
        for cliente in clientes.values():
            novos_parametros, n_amostras, _ = cliente.fit(parametros_globais, {})
            resultados_fit.append((novos_parametros, n_amostras))

        # Agregação real do Flower (média ponderada pelo n_amostras de cada escola)
        parametros_globais = aggregate(resultados_fit)

        acuracias_locais = [
            cliente.evaluate(parametros_globais, {})[2]["acuracia"] for cliente in clientes.values()
        ]
        print(f"  Round {rodada:2d}/{rounds} — acurácia local média: {sum(acuracias_locais)/len(acuracias_locais):.3f}")

    definir_parametros(modelo_global, parametros_globais)
    return modelo_global


def main(rounds: int) -> None:
    particoes = gerar_particoes()
    X_teste, y_teste = montar_conjunto_teste_global()

    print("=== Escolas simuladas (não-IID) ===")
    for escola, (X, y) in particoes.items():
        print(f"  {escola}: {len(X)} amostras, taxa de crise = {y.mean():.1%}")

    print("\n=== Treinamento centralizado ===")
    modelo_centralizado = treinar_centralizado(particoes, epocas=rounds)
    acuracia_centralizado = modelo_centralizado.score(X_teste, y_teste)
    print(f"Acurácia no conjunto de teste global: {acuracia_centralizado:.3f}")

    print(f"\n=== Treinamento federado (FedAvg, {rounds} rounds) ===")
    modelo_federado = treinar_federado(particoes, rounds)
    acuracia_federado = modelo_federado.score(X_teste, y_teste)
    print(f"Acurácia no conjunto de teste global: {acuracia_federado:.3f}")

    print("\n=== Comparação ===")
    diferenca = acuracia_centralizado - acuracia_federado
    print(f"Centralizado: {acuracia_centralizado:.3f}")
    print(f"Federado:     {acuracia_federado:.3f}")
    print(f"Diferença:    {diferenca:+.3f} ({'centralizado melhor' if diferenca > 0 else 'federado melhor ou igual'})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()
    main(args.rounds)
