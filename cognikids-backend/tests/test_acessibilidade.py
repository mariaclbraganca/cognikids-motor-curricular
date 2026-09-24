"""
Perfil funcional de acessibilidade e pedido de pausa.

Verifica que a interface se adapta a necessidades observaveis (sem coletar
diagnostico), que conflitos entre necessidades resolvem para o lado mais
protetivo, e que a crianca tem autonomia dentro de limites.
"""

import pytest

from app.Utils.accessibility import CATALOGO, resolver_tokens


class TestQuestionario:
    def test_lista_perguntas(self, responsavel):
        r = responsavel.get('/api/accessibility/questionnaire')
        assert r.status_code == 200
        assert len(r.get_json()['data']['perguntas']) == len(CATALOGO)

    def test_perguntas_sao_sobre_comportamento_observavel(self, responsavel):
        """Nenhuma pergunta pode citar diagnostico.

        Compara palavra a palavra: 'tea' aparece como substring em 'esteja'
        e geraria falso positivo numa busca ingenua.
        """
        import re

        dados = responsavel.get('/api/accessibility/questionnaire').get_json()['data']
        texto = ' '.join(
            f"{p['pergunta']} {p.get('ajuda') or ''}" for p in dados['perguntas']
        ).lower()
        palavras = set(re.findall(r'\w+', texto))

        proibidas = {'autismo', 'autista', 'tea', 'tdah', 'dislexia', 'dislexico',
                     'transtorno', 'diagnostico', 'laudo', 'sindrome', 'bipolar',
                     'borderline', 'asperger', 'tourette', 'deficit'}

        encontradas = palavras & proibidas
        assert not encontradas, f"questionario menciona diagnostico: {encontradas}"

    def test_informa_o_que_a_crianca_pode_ajustar(self, responsavel):
        dados = responsavel.get('/api/accessibility/questionnaire').get_json()['data']
        assert set(dados['ajustaveis_pela_crianca']) == {
            'estimulo', 'densidade', 'texto'
        }


class TestResolucaoDeTokens:
    """A logica pura, sem HTTP."""

    def test_padrao_conservador_sem_perfil(self):
        tokens = resolver_tokens({})
        assert tokens['estimulo'] == 'medio'
        assert tokens['som'] == 'nenhum'
        assert tokens['linguagem'] == 'literal'

    def test_sensibilidade_reduz_estimulo(self):
        tokens = resolver_tokens({'sensibilidade_sensorial': 'sim'})
        assert tokens['estimulo'] == 'calmo'
        assert tokens['movimento'] == 'nenhum'

    def test_conflito_resolve_para_o_mais_protetivo(self):
        """Necessidades opostas coexistem: vence quem protege mais.

        Cenario real de comorbidade — a crianca evita estimulo sensorial
        mas tambem se desengaja de telas neutras.
        """
        tokens = resolver_tokens({
            'sensibilidade_sensorial': 'sim',   # pede 'calmo'
            'busca_estimulo': 'sim',            # pede 'vivo'
        })
        assert tokens['estimulo'] == 'calmo'

    def test_conflito_de_densidade(self):
        tokens = resolver_tokens({
            'atencao': 'sim',            # pede 'minima'
            'esquece_etapas': 'nao',
        })
        assert tokens['densidade'] == 'minima'

    def test_nao_leitor_recebe_pictograma_e_audio(self):
        tokens = resolver_tokens({'leitura': 'ainda_nao'})
        assert tokens['texto'] == 'so_figura'
        assert tokens['audio_disponivel'] is True

    def test_dificuldade_motora_amplia_alvo(self):
        tokens = resolver_tokens({'coordenacao_motora': 'sim'})
        assert tokens['alvo_toque'] == 'extra_grande'
        assert tokens['confirmar_acoes'] is True

    def test_variacao_de_humor_desliga_sequencias(self):
        """Sem streaks nem comparacao — o dia ruim nao pode ser punido."""
        tokens = resolver_tokens({'variacao_humor': 'sim'})
        assert tokens['sem_sequencias'] is True
        assert tokens['sem_comparacao'] is True

    def test_ajuste_da_crianca_sobrepoe(self):
        tokens = resolver_tokens(
            {'busca_estimulo': 'sim'}, {'estimulo': 'calmo'}
        )
        assert tokens['estimulo'] == 'calmo'

    def test_crianca_nao_desliga_protecao(self):
        """Tokens fora da lista permitida sao ignorados."""
        tokens = resolver_tokens(
            {'coordenacao_motora': 'sim'},
            {'confirmar_acoes': False, 'alvo_toque': 'normal'},
        )
        assert tokens['confirmar_acoes'] is True
        assert tokens['alvo_toque'] == 'extra_grande'


class TestPerfilViaAPI:
    def test_responsavel_configura_perfil(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {
                'sensibilidade_sensorial': 'sim',
                'leitura': 'ainda_nao',
                'atencao': 'sim',
            },
        })
        assert r.status_code == 200

        tokens = r.get_json()['data']['tokens']
        assert tokens['estimulo'] == 'calmo'
        assert tokens['texto'] == 'so_figura'
        assert tokens['densidade'] == 'minima'

    def test_aluno_recebe_os_proprios_tokens(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'sim'},
        })

        r = estudante.get('/api/accessibility/me')
        assert r.status_code == 200
        assert r.get_json()['data']['tokens']['estimulo'] == 'calmo'

    def test_perfil_nao_configurado_devolve_padroes(self, estudante):
        r = estudante.get('/api/accessibility/me')
        assert r.status_code == 200
        assert r.get_json()['data']['configurado'] is False

    def test_dimensoes_sem_nomear_diagnostico(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'sim', 'atencao': 'sim'},
        })
        dimensoes = r.get_json()['data']['dimensoes']
        assert 'sensorial' in dimensoes
        assert 'atencao' in dimensoes

    def test_rejeita_resposta_invalida(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'talvez'},
        })
        assert r.status_code == 400

    def test_responsavel_nao_configura_aluno_alheio(self, responsavel, estudante):
        r = responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'sim'},
        })
        assert r.status_code == 403

    def test_professor_da_turma_consulta_perfil(
        self, professor, turma, vinculo_responsavel, estudante
    ):
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'leitura': 'ainda_nao'},
        })
        r = professor.get(f'/api/accessibility/{estudante.id}')
        assert r.status_code == 200


class TestHistoricoDoPerfil:
    """Versionamento do perfil de acessibilidade (ADR-011, rodada 2)."""

    def test_primeira_configuracao_gera_evento(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'sim'},
        })

        r = vinculo_responsavel.get(f'/api/accessibility/{estudante.id}/history')
        assert r.status_code == 200

        eventos = r.get_json()['data']
        assert len(eventos) == 1
        assert eventos[0]['tipo'] == 'respostas'
        assert eventos[0]['mudancas']['sensibilidade_sensorial'] == {
            'de': None, 'para': 'sim'
        }

    def test_mudanca_registra_de_e_para(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'sim'},
        })
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'sensibilidade_sensorial': 'nao'},
        })

        eventos = vinculo_responsavel.get(
            f'/api/accessibility/{estudante.id}/history'
        ).get_json()['data']

        assert len(eventos) == 2
        # mais recente primeiro
        assert eventos[0]['mudancas']['sensibilidade_sensorial'] == {
            'de': 'sim', 'para': 'nao'
        }

    def test_responder_o_mesmo_nao_gera_evento(self, vinculo_responsavel, estudante):
        corpo = {'respostas': {'sensibilidade_sensorial': 'sim'}}
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json=corpo)
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json=corpo)

        eventos = vinculo_responsavel.get(
            f'/api/accessibility/{estudante.id}/history'
        ).get_json()['data']
        assert len(eventos) == 1

    def test_ajuste_da_crianca_tambem_gera_evento(self, estudante):
        estudante.put('/api/accessibility/me/comfort',
                      json={'ajustes': {'estimulo': 'calmo'}})

        eventos = estudante.get(
            f'/api/accessibility/{estudante.id}/history'
        ).get_json()['data']

        assert len(eventos) == 1
        assert eventos[0]['tipo'] == 'ajustes_crianca'
        assert eventos[0]['autor_id'] == estudante.id

    def test_professor_da_turma_consulta_historico(
        self, professor, turma, vinculo_responsavel, estudante
    ):
        vinculo_responsavel.put(f'/api/accessibility/{estudante.id}', json={
            'respostas': {'leitura': 'ainda_nao'},
        })

        r = professor.get(f'/api/accessibility/{estudante.id}/history')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1

    def test_responsavel_nao_ve_historico_de_aluno_alheio(self, responsavel, estudante):
        r = responsavel.get(f'/api/accessibility/{estudante.id}/history')
        assert r.status_code == 403


class TestPainelDeConforto:
    def test_crianca_ajusta_a_propria_tela(self, estudante):
        r = estudante.put('/api/accessibility/me/comfort',
                          json={'ajustes': {'estimulo': 'calmo'}})
        assert r.status_code == 200
        assert r.get_json()['data']['tokens']['estimulo'] == 'calmo'

    def test_ajuste_persiste(self, estudante):
        estudante.put('/api/accessibility/me/comfort',
                      json={'ajustes': {'densidade': 'minima'}})

        r = estudante.get('/api/accessibility/me')
        assert r.get_json()['data']['tokens']['densidade'] == 'minima'

    def test_ignora_token_fora_do_permitido(self, estudante):
        r = estudante.put('/api/accessibility/me/comfort',
                          json={'ajustes': {'confirmar_acoes': False}})
        assert r.status_code == 200
        assert 'confirmar_acoes' in r.get_json()['ignorados']

    def test_responsavel_nao_usa_painel_da_crianca(self, vinculo_responsavel):
        r = vinculo_responsavel.put('/api/accessibility/me/comfort',
                                    json={'ajustes': {'estimulo': 'calmo'}})
        assert r.status_code == 403


class TestPedidoDePausa:
    @pytest.fixture
    def kit(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/support-kit/{estudante.id}', json={
            'estrategias_calmantes': 'Fone abafador, Sala de calma, Beber agua',
        })
        return True

    def test_opcoes_vem_do_kit_de_apoio(self, kit, estudante):
        r = estudante.get('/api/breaks/options')
        assert r.status_code == 200

        opcoes = r.get_json()['data']['opcoes']
        assert {o['estrategia'] for o in opcoes} == {
            'Fone abafador', 'Sala de calma', 'Beber agua'
        }

    def test_permite_pedir_sem_escolher_estrategia(self, estudante):
        """Em desregulacao, escolher ja pode ser demais."""
        r = estudante.post('/api/breaks', json={})
        assert r.status_code == 201

    def test_pedido_com_estrategia(self, kit, estudante):
        r = estudante.post('/api/breaks', json={'estrategia': 'Fone abafador'})
        assert r.status_code == 201

    def test_professor_ve_pedido_pendente(self, professor, turma, estudante):
        estudante.post('/api/breaks', json={'estrategia': 'Sala de calma'})

        r = professor.get('/api/breaks/pending')
        assert r.status_code == 200
        assert r.get_json()['count'] == 1
        assert r.get_json()['data'][0]['aluno_nome']

    def test_professor_atende_pedido(self, professor, turma, estudante):
        pedido = estudante.post('/api/breaks', json={}).get_json()['pedido_id']

        r = professor.put(f'/api/breaks/{pedido}/acknowledge')
        assert r.status_code == 200

    def test_encerrar_registra_eficacia(self, kit, professor, turma, estudante):
        pedido = estudante.post(
            '/api/breaks', json={'estrategia': 'Fone abafador'}
        ).get_json()['pedido_id']

        assert professor.put(f'/api/breaks/{pedido}/close',
                             json={'resultado': 'ajudou'}).status_code == 200

        opcoes = estudante.get('/api/breaks/options').get_json()['data']['opcoes']
        fone = next(o for o in opcoes if o['estrategia'] == 'Fone abafador')
        assert fone['ajudou'] == 1

    def test_estrategia_eficaz_aparece_primeiro(self, kit, professor, turma, estudante):
        """A que funcionou sobe na lista — personalizacao por historico."""
        pedido = estudante.post(
            '/api/breaks', json={'estrategia': 'Beber agua'}
        ).get_json()['pedido_id']
        professor.put(f'/api/breaks/{pedido}/close', json={'resultado': 'ajudou'})

        opcoes = estudante.get('/api/breaks/options').get_json()['data']['opcoes']
        assert opcoes[0]['estrategia'] == 'Beber agua'

    def test_professor_alheio_nao_ve_pedido(self, outro_professor, turma, estudante):
        estudante.post('/api/breaks', json={})

        r = outro_professor.get('/api/breaks/pending')
        assert r.status_code == 200
        assert r.get_json()['data'] == []

    def test_responsavel_acompanha_pausas_do_filho(
        self, vinculo_responsavel, estudante
    ):
        estudante.post('/api/breaks', json={})

        r = vinculo_responsavel.get(f'/api/breaks/student/{estudante.id}')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1

    def test_professor_nao_pede_pausa(self, professor):
        assert professor.post('/api/breaks', json={}).status_code == 403

    def test_aluno_ve_o_proprio_historico(self, estudante):
        estudante.post('/api/breaks', json={})

        r = estudante.get('/api/breaks/mine')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1
