"""Teste de regressão: a porta de text_mining_pt.py precisa manter a mesma
acurácia validada no notebook (ADR-006, 100% em Bloom's e Simpson's) contra
os conjuntos de teste rotulados em notebooks/dados_avaliacao/. Se este teste
falhar após uma mudança nas tabelas de verbos, a mudança introduziu uma
regressão — reavaliar contra o notebook antes de mesclar.
"""

import json
from pathlib import Path

import pytest

from text_mining_pt import analisar_atividade, classificar_bloom_pt, classificar_simpson_pt

DADOS_AVALIACAO = Path(__file__).parent.parent.parent / "notebooks" / "dados_avaliacao"


def _normalizar_bloom(nivel: str) -> str:
    return nivel.split("_")[0] + ("_default" if "(default)" in nivel else "")


def _normalizar_simpson(nivel: str | None) -> str | None:
    return nivel.split("_")[0] if nivel else None


def _carregar_casos(nome_arquivo: str) -> list[tuple[str, str]]:
    caminho = DADOS_AVALIACAO / nome_arquivo
    with caminho.open(encoding="utf-8") as f:
        return json.load(f)


def test_classificador_bloom_mantem_acuracia_do_notebook():
    casos = _carregar_casos("teste_bloom_pt.json")
    erros = [
        (texto, esperado, nivel)
        for texto, esperado in casos
        for nivel, _ in [classificar_bloom_pt(texto)]
        if _normalizar_bloom(nivel) != esperado
    ]
    assert erros == [], f"{len(erros)}/{len(casos)} casos divergem do rótulo esperado: {erros}"


def test_classificador_simpson_mantem_acuracia_do_notebook():
    casos = _carregar_casos("teste_simpson_pt.json")
    erros = [
        (texto, esperado, nivel)
        for texto, esperado in casos
        for nivel, _ in [classificar_simpson_pt(texto)]
        if _normalizar_simpson(nivel) != esperado
    ]
    assert erros == [], f"{len(erros)}/{len(casos)} casos divergem do rótulo esperado: {erros}"


def test_analisar_atividade_combina_as_tres_dimensoes():
    resultado = analisar_atividade(
        "Explique por que as plantas precisam de luz solar para sobreviver, "
        "comparando com a respiração celular, e depois monte uma maquete do processo."
    )
    assert resultado["intencao_pedagogica_bloom"] == "BT2_entender"
    assert resultado["demanda_psicomotora_simpson"] == "S4_mecanismo"
    assert resultado["complexidade"]["contagem_palavras"] > 0


def test_avaliar_complexidade_pt_lida_com_texto_vazio():
    resultado = analisar_atividade("")
    assert resultado["complexidade"] == {"indice_flesch_pt": None, "contagem_palavras": 0}
    assert resultado["intencao_pedagogica_bloom"] == "BT1_lembrar (default)"
    assert resultado["demanda_psicomotora_simpson"] is None
