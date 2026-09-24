"""Modelo (SGDClassifier) + adaptação pra parâmetros no formato que o
Flower espera (lista de arrays numpy) — padrão documentado do Flower pra
modelos scikit-learn, que não tem pesos internos como uma rede neural.

Usa SGDClassifier com `partial_fit` (poucas épocas locais por rodada), não
LogisticRegression.fit() — LogisticRegression converge inteiro a cada
chamada (é um problema convexo), então o ponto de partida (os parâmetros
globais recebidos) não faz diferença no resultado final e o FedAvg vira só
"treinar N modelos isolados e tirar a média uma vez", sem dinâmica real de
rodadas. `partial_fit` faz um número controlado de passos de gradiente por
chamada — é assim que o FedAvg de verdade funciona (poucas épocas locais,
agregação, repete), e é o padrão usado nos tutoriais oficiais do Flower com
scikit-learn.
"""

import numpy as np
from flwr.client import NumPyClient
from sklearn.linear_model import SGDClassifier

N_FEATURES = 3  # bpm, gsr, movimento
CLASSES = np.array([0, 1])
EPOCAS_LOCAIS_POR_RODADA = 1


def criar_modelo() -> SGDClassifier:
    modelo = SGDClassifier(loss="log_loss", learning_rate="optimal", random_state=42)
    definir_parametros_iniciais(modelo)
    return modelo


def definir_parametros_iniciais(modelo: SGDClassifier) -> None:
    """SGDClassifier não tem coef_/intercept_ até o primeiro partial_fit() —
    define manualmente pra poder receber pesos globais antes de treinar
    localmente (é assim que o cliente recebe o modelo do round anterior)."""
    modelo.classes_ = CLASSES
    modelo.coef_ = np.zeros((1, N_FEATURES))
    modelo.intercept_ = np.zeros(1)
    modelo.t_ = 1.0  # contador interno do SGD, usado no learning_rate="optimal"


def obter_parametros(modelo: SGDClassifier) -> list[np.ndarray]:
    return [modelo.coef_, modelo.intercept_]


def definir_parametros(modelo: SGDClassifier, parametros: list[np.ndarray]) -> None:
    modelo.coef_ = parametros[0]
    modelo.intercept_ = parametros[1]


class ClienteEscola(NumPyClient):
    """Um cliente Flower = uma escola. O dado (X, y) nunca sai daqui — só os
    parâmetros do modelo (coef_/intercept_) trafegam, conforme ADR-004."""

    def __init__(self, X: np.ndarray, y: np.ndarray, epocas_locais: int = EPOCAS_LOCAIS_POR_RODADA):
        self.X = X
        self.y = y
        self.epocas_locais = epocas_locais
        self.modelo = criar_modelo()

    def get_parameters(self, config):
        return obter_parametros(self.modelo)

    def fit(self, parameters, config):
        definir_parametros(self.modelo, parameters)
        for _ in range(self.epocas_locais):
            self.modelo.partial_fit(self.X, self.y, classes=CLASSES)
        return obter_parametros(self.modelo), len(self.X), {}

    def evaluate(self, parameters, config):
        definir_parametros(self.modelo, parameters)
        acuracia = self.modelo.score(self.X, self.y)
        return 1 - acuracia, len(self.X), {"acuracia": acuracia}
