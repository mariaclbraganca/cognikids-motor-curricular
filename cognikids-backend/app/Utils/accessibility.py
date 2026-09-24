"""
Perfil funcional de acessibilidade.

Este modulo traduz NECESSIDADES OBSERVAVEIS em TOKENS DE INTERFACE.

Decisao de projeto: o sistema nao pergunta nem armazena diagnostico.
Motivos:

1. Diagnostico nao determina necessidade de interface. Duas criancas com o
   mesmo laudo de TEA podem ter perfis sensoriais opostos (uma busca
   estimulo, outra evita) — a variacao dentro de um diagnostico costuma ser
   maior que entre diagnosticos.
2. Comorbidade e a regra (TEA+TDAH, dislexia+TDAH). Presets por diagnostico
   entram em conflito direto e nao se somam.
3. Diagnostico e dado pessoal sensivel de saude de menor (LGPD art. 11).
   Perguntar "ele se incomoda com sons altos?" obtem o que a interface
   precisa sem coletar categoria especial de dado.

O responsavel responde sobre o que observa no dia a dia. Cada resposta
mapeia para tokens que o front aplica no <html>.
"""

# --------------------------------------------------------------------------
# Catalogo de necessidades
# --------------------------------------------------------------------------
# Cada necessidade tem:
#   id        chave persistida
#   pergunta  texto exibido ao responsavel (linguagem observavel, sem jargao)
#   ajuda     esclarecimento opcional
#   opcoes    respostas possiveis, cada uma com os tokens que aplica
#
# 'tokens' usa nomes neutros de interface. O front resolve para CSS.

ESCALA_PADRAO = 'escala'      # nao / as vezes / sim
ESCALA_BINARIA = 'binaria'    # nao / sim

CATALOGO = [
    {
        'id': 'sensibilidade_sensorial',
        'dimensao': 'sensorial',
        'pergunta': 'Ela se incomoda com sons altos, luzes fortes ou muitas cores?',
        'ajuda': 'Por exemplo: tapa os ouvidos, evita lugares barulhentos, reclama de luz.',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {'estimulo': 'vivo'}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'estimulo': 'medio'}},
            {'valor': 'sim', 'rotulo': 'Sim', 'tokens': {'estimulo': 'calmo', 'movimento': 'nenhum', 'som': 'nenhum'}},
        ],
    },
    {
        'id': 'busca_estimulo',
        'dimensao': 'sensorial',
        'pergunta': 'Ela perde o interesse rapido quando algo e muito parado ou sem cor?',
        'ajuda': 'Criancas que buscam estimulo costumam se desengajar de telas muito neutras.',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'estimulo': 'medio'}},
            {'valor': 'sim', 'rotulo': 'Sim', 'tokens': {'estimulo': 'vivo'}},
        ],
    },
    {
        'id': 'leitura',
        'dimensao': 'linguagem',
        'pergunta': 'Ela le sozinha com facilidade?',
        'ajuda': 'Vale para leitura de frases curtas, nao de textos longos.',
        'tipo': 'leitura',
        'opcoes': [
            {'valor': 'ainda_nao', 'rotulo': 'Ainda nao le',
             'tokens': {'texto': 'so_figura', 'audio_disponivel': True}},
            {'valor': 'com_ajuda', 'rotulo': 'Le com esforco ou ajuda',
             'tokens': {'texto': 'figura_e_letra', 'audio_disponivel': True,
                        'fonte_ampliada': True}},
            {'valor': 'sim', 'rotulo': 'Le sozinha', 'tokens': {'texto': 'figura_e_letra'}},
        ],
    },
    {
        'id': 'textos_longos',
        'dimensao': 'linguagem',
        'pergunta': 'Ela se cansa ou se perde quando o texto e longo?',
        'ajuda': 'Por exemplo: desiste no meio, pula linhas, pede para alguem ler.',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'espacamento': 'amplo'}},
            # 'texto': 'so_figura' saiu daqui de proposito. Cansar-se de texto
            # longo se trata FATIANDO (passo_unico), nao REMOVENDO a letra:
            # combinado com leitura='com_ajuda', o valor anterior resolvia para
            # so_figura e a crianca que le com esforco perdia a letra por
            # completo — perdia pratica de leitura por ter respondido com
            # honestidade sobre fadiga. Quem realmente nao le chega a so_figura
            # pelas perguntas 'leitura' e 'comunicacao_verbal', que e onde essa
            # decisao pertence.
            {'valor': 'sim', 'rotulo': 'Sim',
             'tokens': {'espacamento': 'amplo', 'passo_unico': True,
                        'audio_disponivel': True}},
        ],
    },
    {
        'id': 'atencao',
        'dimensao': 'atencao',
        'pergunta': 'Ela se distrai facil quando ha muita coisa na tela?',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {'densidade': 'completa'}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'densidade': 'media'}},
            {'valor': 'sim', 'rotulo': 'Sim',
             'tokens': {'densidade': 'minima', 'movimento': 'nenhum'}},
        ],
    },
    {
        'id': 'esquece_etapas',
        'dimensao': 'atencao',
        'pergunta': 'Ela esquece o que ia fazer no meio de uma tarefa?',
        'ajuda': 'Relacionado a memoria de trabalho e funcao executiva.',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'lembretes': True}},
            {'valor': 'sim', 'rotulo': 'Sim',
             'tokens': {'lembretes': True, 'passo_unico': True, 'densidade': 'minima'}},
        ],
    },
    {
        'id': 'nocao_de_tempo',
        'dimensao': 'atencao',
        'pergunta': 'Ela tem dificuldade de perceber quanto tempo passou?',
        'ajuda': 'Por exemplo: nao percebe que ja se passaram 20 minutos.',
        'tipo': ESCALA_BINARIA,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'sim', 'rotulo': 'Sim', 'tokens': {'tempo_visual': True}},
        ],
    },
    {
        'id': 'mudancas_rotina',
        'dimensao': 'previsibilidade',
        'pergunta': 'Mudancas inesperadas deixam ela desconfortavel?',
        'ajuda': 'Por exemplo: mudar a ordem das coisas sem avisar.',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'avisar_mudanca': True}},
            {'valor': 'sim', 'rotulo': 'Sim',
             'tokens': {'avisar_mudanca': True, 'navegacao': 'fixa', 'movimento': 'nenhum'}},
        ],
    },
    {
        'id': 'linguagem_literal',
        'dimensao': 'previsibilidade',
        'pergunta': 'Ela entende melhor quando se fala de forma direta e literal?',
        'ajuda': 'Dificuldade com ironia, metafora ou expressoes como "quebrar o gelo".',
        'tipo': ESCALA_BINARIA,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'sim', 'rotulo': 'Sim', 'tokens': {'linguagem': 'literal'}},
        ],
    },
    {
        'id': 'coordenacao_motora',
        'dimensao': 'motor',
        'pergunta': 'Ela tem dificuldade para acertar botoes pequenos na tela?',
        'ajuda': 'Vale tambem se ela tem movimentos involuntarios (tiques).',
        'tipo': ESCALA_PADRAO,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes', 'tokens': {'alvo_toque': 'grande'}},
            {'valor': 'sim', 'rotulo': 'Sim',
             'tokens': {'alvo_toque': 'extra_grande', 'confirmar_acoes': True}},
        ],
    },
    {
        'id': 'variacao_humor',
        'dimensao': 'afetivo',
        'pergunta': 'O humor dela varia bastante de um dia para o outro?',
        'ajuda': 'Isso ajuda o app a evitar comparacoes entre dias e metas de sequencia.',
        'tipo': ESCALA_BINARIA,
        'opcoes': [
            {'valor': 'nao', 'rotulo': 'Nao', 'tokens': {}},
            {'valor': 'sim', 'rotulo': 'Sim',
             'tokens': {'sem_sequencias': True, 'sem_comparacao': True}},
        ],
    },
    {
        'id': 'comunicacao_verbal',
        'dimensao': 'linguagem',
        'pergunta': 'Ela consegue dizer com palavras como esta se sentindo?',
        'tipo': 'comunicacao',
        'opcoes': [
            {'valor': 'raramente', 'rotulo': 'Raramente',
             'tokens': {'texto': 'so_figura', 'entrada': 'pictograma'}},
            {'valor': 'as_vezes', 'rotulo': 'As vezes',
             'tokens': {'entrada': 'pictograma'}},
            {'valor': 'sim', 'rotulo': 'Sim, com facilidade', 'tokens': {}},
        ],
    },
]

# --------------------------------------------------------------------------
# Resolucao de tokens
# --------------------------------------------------------------------------

# Padroes conservadores: aplicados quando nao ha perfil preenchido.
# A escolha e deliberada — na duvida, menos estimulo e mais suporte.
TOKENS_PADRAO = {
    'estimulo': 'medio',
    'densidade': 'media',
    'texto': 'figura_e_letra',
    'movimento': 'reduzido',
    'som': 'nenhum',
    'alvo_toque': 'grande',
    'espacamento': 'normal',
    'navegacao': 'fixa',
    'linguagem': 'literal',
    'entrada': 'pictograma',
    'audio_disponivel': False,
    'fonte_ampliada': False,
    'lembretes': False,
    'passo_unico': False,
    'tempo_visual': False,
    'avisar_mudanca': True,
    'sem_sequencias': False,
    'sem_comparacao': False,
    'confirmar_acoes': False,
}

# Quando duas respostas pedem valores diferentes do mesmo token, vence o
# mais conservador. Ordem = do mais protetivo ao menos protetivo.
PRECEDENCIA = {
    'estimulo': ['calmo', 'medio', 'vivo'],
    'densidade': ['minima', 'media', 'completa'],
    'texto': ['so_figura', 'figura_e_letra'],
    'movimento': ['nenhum', 'reduzido', 'completo'],
    'som': ['nenhum', 'sob_demanda'],
    'alvo_toque': ['extra_grande', 'grande', 'normal'],
    'espacamento': ['amplo', 'normal'],
    'navegacao': ['fixa', 'livre'],
    'linguagem': ['literal', 'livre'],
    'entrada': ['pictograma', 'texto'],
}

# Ajustes que a propria crianca pode alterar no painel de conforto.
# Os demais tokens sao definidos pelo responsavel e nao aparecem para ela:
# mexer em 'confirmar_acoes' ou 'sem_sequencias' exige contexto que a
# crianca nao tem, e um toque acidental nao pode desfazer uma protecao.
AJUSTAVEIS_PELA_CRIANCA = ('estimulo', 'densidade', 'texto')


def _mais_conservador(token, atual, novo):
    """Resolve conflito entre dois valores do mesmo token."""
    ordem = PRECEDENCIA.get(token)
    if not ordem:
        # Tokens booleanos: True (mais suporte) sempre vence
        if isinstance(atual, bool) or isinstance(novo, bool):
            return bool(atual) or bool(novo)
        return novo

    if atual not in ordem:
        return novo
    if novo not in ordem:
        return atual
    return atual if ordem.index(atual) <= ordem.index(novo) else novo


def catalogo_publico():
    """Catalogo para o front montar o questionario."""
    return [
        {
            'id': item['id'],
            'dimensao': item['dimensao'],
            'pergunta': item['pergunta'],
            'ajuda': item.get('ajuda'),
            'tipo': item['tipo'],
            'opcoes': [
                {'valor': o['valor'], 'rotulo': o['rotulo']} for o in item['opcoes']
            ],
        }
        for item in CATALOGO
    ]


def validar_respostas(respostas):
    """Valida as respostas do questionario.

    Retorna (respostas_validas, erros). Chaves desconhecidas sao ignoradas
    silenciosamente; valores invalidos viram erro explicito.
    """
    if not isinstance(respostas, dict):
        return {}, ['As respostas devem ser um objeto']

    por_id = {item['id']: item for item in CATALOGO}
    validas = {}
    erros = []

    for chave, valor in respostas.items():
        item = por_id.get(chave)
        if not item:
            continue
        permitidos = [o['valor'] for o in item['opcoes']]
        if valor not in permitidos:
            erros.append(
                f"Resposta invalida para '{chave}': use um de {', '.join(permitidos)}"
            )
            continue
        validas[chave] = valor

    return validas, erros


def resolver_tokens(respostas, ajustes_crianca=None):
    """Converte respostas em tokens de interface.

    Args:
        respostas: {id_necessidade: valor}
        ajustes_crianca: preferencias da propria crianca; so os tokens em
            AJUSTAVEIS_PELA_CRIANCA sao considerados.

    Returns:
        dict de tokens prontos para o front aplicar.
    """
    # As respostas se conciliam ENTRE SI (o mais conservador entre elas); o
    # padrao so preenche o que nenhuma resposta declarou. Antes, cada
    # resposta era comparada direto contra TOKENS_PADRAO — que ja nasce quase
    # no extremo protetivo — entao uma unica resposta pedindo algo menos
    # protetivo nunca vencia, mesmo sem nenhuma outra resposta pedindo mais
    # protecao. Auditoria do conselho (ADR-011): 3 respostas legitimas
    # (ex.: nao ter sensibilidade sensorial nenhuma) ficavam sem efeito por
    # essa causa. Comparar so entre respostas corrige os 3 casos sem afrouxar
    # a protecao quando ha conflito real (ex.: TEA + busca de estimulo
    # continua resolvendo para o mais calmo).
    declarados = {}
    por_id = {item['id']: item for item in CATALOGO}

    for chave, valor in (respostas or {}).items():
        item = por_id.get(chave)
        if not item:
            continue

        opcao = next((o for o in item['opcoes'] if o['valor'] == valor), None)
        if not opcao:
            continue

        for token, novo in opcao.get('tokens', {}).items():
            if token in declarados:
                declarados[token] = _mais_conservador(token, declarados[token], novo)
            else:
                declarados[token] = novo

    tokens = dict(TOKENS_PADRAO)
    tokens.update(declarados)

    # A crianca ajusta por cima, dentro dos limites permitidos
    for token, valor in (ajustes_crianca or {}).items():
        if token in AJUSTAVEIS_PELA_CRIANCA:
            ordem = PRECEDENCIA.get(token, [])
            if not ordem or valor in ordem:
                tokens[token] = valor

    return tokens


def dimensoes_atendidas(respostas):
    """Dimensoes em que a resposta produziu EFEITO REAL na interface.

    Serve para o responsavel e o professor entenderem o perfil sem que o
    sistema nomeie nenhum diagnostico.

    A versao anterior olhava os tokens DECLARADOS na opcao, nao o efeito. Como
    TOKENS_PADRAO ja nasce quase no extremo protetivo e _mais_conservador
    nunca afrouxa, varias respostas declaram um token e nao mudam nada — e a
    dimensao era reportada como atendida mesmo assim. Medido: 'busca_estimulo'
    e 'linguagem_literal' nao alteram token nenhum sob nenhuma resposta, e
    ainda assim marcavam 'sensorial' e 'previsibilidade'.

    Isso importa alem da UI: a escola usa este campo como evidencia de
    adaptacao razoavel (LBI art. 3o, III), que se afere pelo efeito concreto.
    Reportar dimensao sem efeito e registro falso.
    """
    por_id = {item['id']: item for item in CATALOGO}
    padrao = resolver_tokens({})
    dimensoes = set()

    for chave, valor in (respostas or {}).items():
        item = por_id.get(chave)
        if not item:
            continue
        resolvidos = resolver_tokens({chave: valor})
        if any(padrao.get(token) != v for token, v in resolvidos.items()):
            dimensoes.add(item['dimensao'])

    return sorted(dimensoes)


def respostas_sem_efeito(respostas):
    """Respostas que o responsavel deu e que nao mudaram nada na interface.

    Existe para a UI poder ser honesta com quem respondeu: sem isso, o
    responsavel preenche o questionario e nunca descobre que parte do que ele
    declarou foi descartado.

    A pergunta certa nao e "esta resposta, sozinha, difere do padrao?" — e
    "se eu tirasse so esta resposta, o resultado final mudaria?" (retirada
    isolada, contra o conjunto completo de respostas). Sao coisas diferentes:
    apos a correcao de precedencia (ADR-011), 'busca_estimulo=sim' passou a
    ter efeito SOZINHA (pede estimulo:vivo). Mas se o responsavel tambem
    respondeu 'sensibilidade_sensorial=sim' (que pede calmo, mais protetivo),
    o resultado final e calmo com ou sem a resposta de busca_estimulo — ela
    continua sem efeito NAQUELE contexto, e e isso que a pessoa precisa saber.

    Retorna [{id, dimensao, valor, motivo}].
    """
    por_id = {item['id']: item for item in CATALOGO}
    padrao = resolver_tokens({})
    completo = resolver_tokens(respostas)
    sem_efeito = []

    for chave, valor in (respostas or {}).items():
        item = por_id.get(chave)
        if not item:
            continue
        opcao = next((o for o in item['opcoes'] if o['valor'] == valor), None)
        if not opcao:
            continue

        sem_esta_resposta = {k: v for k, v in respostas.items() if k != chave}
        resultado_sem_ela = resolver_tokens(sem_esta_resposta)
        if resultado_sem_ela != completo:
            continue  # tirar esta resposta muda o resultado -> ela importa

        pedidos = opcao.get('tokens', {})
        isolada = resolver_tokens({chave: valor})
        tem_efeito_isolado = any(padrao.get(t) != v for t, v in isolada.items())

        if not pedidos:
            motivo = 'esta resposta nao pede nenhum ajuste'
        elif not tem_efeito_isolado:
            motivo = 'a configuracao padrao ja e igual ou mais protetiva'
        else:
            motivo = 'outra resposta ja garante protecao igual ou maior'

        sem_efeito.append({
            'id': chave,
            'dimensao': item['dimensao'],
            'valor': valor,
            'motivo': motivo,
        })

    return sem_efeito
