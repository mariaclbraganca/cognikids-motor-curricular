import numpy as np

from fl_dataset import gerar_dados_escola
from fl_model import ClienteEscola, criar_modelo, definir_parametros, obter_parametros


def test_obter_e_definir_parametros_fazem_round_trip():
    modelo = criar_modelo()
    parametros = obter_parametros(modelo)

    modelo2 = criar_modelo()
    definir_parametros(modelo2, [p + 1 for p in parametros])

    assert (modelo2.coef_ == parametros[0] + 1).all()
    assert (modelo2.intercept_ == parametros[1] + 1).all()


def test_fit_do_cliente_muda_os_parametros():
    X, y = gerar_dados_escola("escola_a", 200, seed=1)
    cliente = ClienteEscola(X, y)

    parametros_iniciais = obter_parametros(cliente.modelo)
    novos_parametros, n_amostras, _ = cliente.fit([p.copy() for p in parametros_iniciais], {})

    assert n_amostras == 200
    assert not np.array_equal(novos_parametros[0], parametros_iniciais[0])


def test_fit_do_cliente_nunca_expoe_x_ou_y_no_retorno():
    """Verificação direta da regra da ADR-004: só parâmetros trafegam, nunca
    o dado bruto do aluno."""
    X, y = gerar_dados_escola("escola_a", 50, seed=1)
    cliente = ClienteEscola(X, y)

    retorno = cliente.fit(obter_parametros(cliente.modelo), {})

    assert len(retorno) == 3
    parametros, n_amostras, metricas = retorno
    assert isinstance(n_amostras, int)
    assert all(isinstance(p, np.ndarray) and p.shape in {(1, 3), (1,)} for p in parametros)


def test_evaluate_retorna_acuracia_entre_0_e_1():
    X, y = gerar_dados_escola("escola_a", 100, seed=1)
    cliente = ClienteEscola(X, y)
    cliente.fit(obter_parametros(cliente.modelo), {})

    _, _, metricas = cliente.evaluate(obter_parametros(cliente.modelo), {})

    assert 0.0 <= metricas["acuracia"] <= 1.0
