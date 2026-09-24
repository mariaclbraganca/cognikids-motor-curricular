from fl_dataset import PERFIS_POR_ESCOLA, gerar_dados_escola, gerar_particoes


def test_gerar_dados_escola_retorna_tamanho_pedido():
    X, y = gerar_dados_escola("escola_a", 100, seed=1)
    assert X.shape == (100, 3)
    assert y.shape == (100,)


def test_gerar_dados_escola_e_deterministico_pela_seed():
    X1, y1 = gerar_dados_escola("escola_a", 50, seed=7)
    X2, y2 = gerar_dados_escola("escola_a", 50, seed=7)
    assert (X1 == X2).all()
    assert (y1 == y2).all()


def test_escolas_com_maior_proporcao_ansiosa_tem_mais_crise():
    """Não-IID de propósito — é o que torna o experimento federado vs.
    centralizado interessante (ver docstring de fl_dataset.py)."""
    taxas = {}
    for escola in PERFIS_POR_ESCOLA:
        _, y = gerar_dados_escola(escola, 2000, seed=123)
        taxas[escola] = y.mean()

    proporcoes_ansioso = [PERFIS_POR_ESCOLA[e]["prop_ansioso"] for e in PERFIS_POR_ESCOLA]
    assert proporcoes_ansioso == sorted(proporcoes_ansioso)  # ordem de escola_a a escola_d é crescente
    taxas_em_ordem = [taxas[e] for e in PERFIS_POR_ESCOLA]
    assert taxas_em_ordem == sorted(taxas_em_ordem)


def test_gerar_particoes_retorna_uma_por_escola():
    particoes = gerar_particoes(n_amostras_por_escola=50)
    assert set(particoes.keys()) == set(PERFIS_POR_ESCOLA.keys())
    for X, y in particoes.values():
        assert len(X) == 50
