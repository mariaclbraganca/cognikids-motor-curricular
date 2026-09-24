"""Regressao das correcoes apontadas pelo conselho de especialistas.

Cada teste abaixo falha se o defeito voltar. Todos foram medidos rodando o
codigo antes da correcao, nao inferidos.
"""

from app.Models.consent_model import USO_PESQUISA, Consent
from app.Utils.accessibility import (
    CATALOGO,
    dimensoes_atendidas,
    resolver_tokens,
    respostas_sem_efeito,
)


# --------------------------------------------------------------------------
# dimensoes_atendidas afirmava adequacao que nao acontecia
# --------------------------------------------------------------------------

def test_dimensao_so_e_atendida_quando_ha_efeito_real():
    """Casos legitimamente inertes: a opcao nao declara token nenhum, ou
    declara exatamente o que ja e o padrao. Nesses, a dimensao nao pode ser
    reportada como atendida — reportar seria registro falso, ja que a escola
    usa este campo como evidencia de adaptacao razoavel (LBI art. 3o, III),
    que se afere pelo efeito concreto.

    ('busca_estimulo', 'sensibilidade_sensorial' e 'atencao=nao' saíram desta
    lista porque a correcao de precedencia (ADR-011) fez elas passarem a ter
    efeito real quando respondidas isoladamente — ver
    test_precedencia_compara_respostas_entre_si_nao_so_contra_o_padrao.)
    """
    padrao = resolver_tokens({})

    for respostas in (
        {'esquece_etapas': 'nao'},
        {'linguagem_literal': 'sim'},
        {'coordenacao_motora': 'as_vezes'},
        {'mudancas_rotina': 'nao'},
    ):
        tokens = resolver_tokens(respostas)
        sem_efeito = all(padrao.get(k) == v for k, v in tokens.items())
        assert sem_efeito, f'premissa do teste mudou: {respostas} agora tem efeito'
        assert dimensoes_atendidas(respostas) == [], (
            f'REGRESSAO: {respostas} afirma dimensao sem mudar token nenhum'
        )


def test_precedencia_compara_respostas_entre_si_nao_so_contra_o_padrao():
    """ADR-011: 3 respostas legitimas ficavam sem efeito porque eram
    comparadas contra TOKENS_PADRAO (ja quase no extremo protetivo) em vez de
    contra as OUTRAS respostas. Corrigido: o padrao so preenche o que nenhuma
    resposta declarou. Estes 3 casos passam a ter efeito, e a protecao real
    (conflito TEA+TDAH) continua de pe.
    """
    for respostas, token, esperado in (
        ({'sensibilidade_sensorial': 'nao'}, 'estimulo', 'vivo'),
        ({'busca_estimulo': 'sim'}, 'estimulo', 'vivo'),
        ({'atencao': 'nao'}, 'densidade', 'completa'),
    ):
        tokens = resolver_tokens(respostas)
        assert tokens[token] == esperado, (
            f'REGRESSAO: {respostas} deveria produzir {token}={esperado}, '
            f'veio {tokens[token]}'
        )

    # Com sinal conflitante de verdade, o mais conservador ainda vence.
    conflito = resolver_tokens({
        'sensibilidade_sensorial': 'sim', 'busca_estimulo': 'sim',
    })
    assert conflito['estimulo'] == 'calmo', (
        'REGRESSAO: a correcao de precedencia afrouxou protecao real (TEA+TDAH)'
    )


def test_dimensao_continua_sendo_reportada_quando_ha_efeito():
    """A correcao nao pode ter zerado o caso legitimo."""
    assert dimensoes_atendidas({'sensibilidade_sensorial': 'sim'}) == ['sensorial']
    assert dimensoes_atendidas({'esquece_etapas': 'sim'}) == ['atencao']


def test_respostas_sem_efeito_sao_expostas_para_a_ui():
    """O responsavel precisa poder ver o que ele declarou e nao foi aplicado."""
    sem_efeito = respostas_sem_efeito({
        'busca_estimulo': 'sim',
        'sensibilidade_sensorial': 'sim',
    })

    ids = {item['id'] for item in sem_efeito}
    assert ids == {'busca_estimulo'}
    assert sem_efeito[0]['motivo']


# --------------------------------------------------------------------------
# textos_longos apagava a letra de quem le com esforco
# --------------------------------------------------------------------------

def test_quem_le_com_esforco_nao_perde_a_letra():
    """Antes: leitura=com_ajuda + textos_longos=sim resolvia para so_figura.

    Cansaco com texto longo se trata fatiando, nao removendo a letra.
    """
    tokens = resolver_tokens({'leitura': 'com_ajuda', 'textos_longos': 'sim'})

    assert tokens['texto'] == 'figura_e_letra', (
        'REGRESSAO: a crianca que le com esforco voltou a perder a letra'
    )
    assert tokens['passo_unico'] is True, 'o texto longo deve ser fatiado'
    assert tokens['espacamento'] == 'amplo'
    assert tokens['audio_disponivel'] is True


def test_quem_nao_le_continua_recebendo_so_figura():
    """A correcao nao pode ter tirado o pictograma de quem precisa dele."""
    assert resolver_tokens({'leitura': 'ainda_nao'})['texto'] == 'so_figura'
    assert resolver_tokens({'comunicacao_verbal': 'raramente'})['texto'] == 'so_figura'


# --------------------------------------------------------------------------
# uso_pesquisa prometia anonimizacao inexistente
# --------------------------------------------------------------------------

def test_uso_pesquisa_nao_pode_ser_concedido(app, db, estudante, responsavel):
    """Nada no codigo desidentifica nada, e nao ha aprovacao de CEP."""
    estado, avisos = Consent().registrar(
        estudante.oid, {'uso_app': True, USO_PESQUISA: True}, responsavel.oid
    )

    assert estado[USO_PESQUISA] is False, (
        'REGRESSAO: uso_pesquisa voltou a ser concedivel sem CEP nem anonimizacao'
    )
    assert any('indisponivel' in aviso.lower() for aviso in avisos)


def test_uso_pesquisa_continua_visivel_no_termo():
    """Some-la esconderia do responsavel que a finalidade existiu."""
    termo = Consent.termo_publico()
    pesquisa = next(f for f in termo['finalidades'] if f['id'] == USO_PESQUISA)

    assert pesquisa['disponivel'] is False
    assert 'Comite de Etica' in pesquisa['descricao']


def test_demais_finalidades_continuam_disponiveis():
    termo = Consent.termo_publico()
    disponiveis = {f['id'] for f in termo['finalidades'] if f['disponivel']}
    assert disponiveis == {'uso_app', 'coleta_biometrica', 'compartilhar_escola'}


# --------------------------------------------------------------------------
# integridade do catalogo
# --------------------------------------------------------------------------

def test_catalogo_nao_perdeu_perguntas():
    assert len(CATALOGO) == 12
    assert len({item['dimensao'] for item in CATALOGO}) == 6
