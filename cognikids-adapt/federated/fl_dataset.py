"""Dados sintéticos para o experimento de Federated Learning (Sprint 3).

Mesma ideia de base biométrica (BPM + GSR + movimento → risco de crise) do
Random Forest do core (`cognikids-backend/scripts/utils/train_model.py`),
mas particionada em N "escolas" com misturas de perfil diferentes entre si
(não-IID) — se as escolas fossem idênticas, comparar federado vs.
centralizado seria pouco interessante (os dois dariam praticamente o mesmo
resultado por construção). Dados sintéticos, sem nenhum dado real de
criança (ver ADR-003 no CLAUDE.md — mesma regra do core).
"""

import numpy as np

# Cada escola tem uma proporção diferente de alunos "tranquilos" vs.
# "ansiosos" — controla o quão não-IID a base fica entre escolas.
PERFIS_POR_ESCOLA = {
    "escola_a": {"prop_ansioso": 0.15},
    "escola_b": {"prop_ansioso": 0.30},
    "escola_c": {"prop_ansioso": 0.55},
    "escola_d": {"prop_ansioso": 0.75},
}


def _gerar_amostra(rng: np.random.Generator, ansioso: bool) -> tuple[list[float], int]:
    if ansioso:
        bpm = rng.uniform(95, 175)
        gsr = rng.uniform(1.2, 5.5)
        movimento = rng.uniform(0.0, 3.0)
        crise = 1 if (bpm > 130 and gsr > 2.5) else int(rng.random() < 0.1)
    else:
        bpm = rng.uniform(55, 110)
        gsr = rng.uniform(0.1, 1.5)
        movimento = rng.uniform(0.1, 2.0)
        crise = 1 if (bpm > 100 and gsr > 1.2) else int(rng.random() < 0.03)

    return [bpm, gsr, movimento], crise


def gerar_dados_escola(nome_escola: str, n_amostras: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Gera (X, y) para uma escola, seguindo a proporção ansioso/tranquilo dela."""
    rng = np.random.default_rng(seed)
    prop_ansioso = PERFIS_POR_ESCOLA[nome_escola]["prop_ansioso"]

    X, y = [], []
    for _ in range(n_amostras):
        ansioso = rng.random() < prop_ansioso
        features, crise = _gerar_amostra(rng, ansioso)
        X.append(features)
        y.append(crise)

    return np.array(X), np.array(y)


def gerar_particoes(n_amostras_por_escola: int = 400, seed_base: int = 42) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Uma partição (X, y) por escola — é isso que cada cliente federado usa,
    sem nunca ver o dado das outras escolas."""
    return {
        escola: gerar_dados_escola(escola, n_amostras_por_escola, seed_base + i)
        for i, escola in enumerate(PERFIS_POR_ESCOLA)
    }
