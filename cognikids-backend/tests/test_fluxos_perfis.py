"""
Fluxos ponta a ponta de cada perfil.

Cada classe percorre o caminho completo que aquele usuario faz no sistema,
provando que as funcionalidades estao acessiveis de fato — e nao apenas que
as rotas existem.
"""

import pytest
from bson.objectid import ObjectId


class TestFluxoProfessor:
    def test_cria_turma_e_ela_aparece_na_listagem(self, professor):
        r = professor.post('/api/classes', json={
            'name': '5o Ano B', 'grade': '5o Ano', 'section': 'B', 'school_year': '2026',
        })
        assert r.status_code == 201

        listagem = professor.get('/api/classes').get_json()['data']
        assert any(t['name'] == '5o Ano B' for t in listagem)

    def test_cria_aluno_e_ele_fica_matriculado(self, professor, turma, db):
        r = professor.post('/api/students', json={
            'nome': 'Novo Aluno', 'email': 'novo@x.com',
            'senha': 'senha123', 'turma_id': str(turma),
        })
        assert r.status_code == 201

        aluno_id = ObjectId(r.get_json()['student_id'])
        assert db.users.find_one({'_id': aluno_id})['tipo'] == 'estudante'
        assert aluno_id in db.turmas.find_one({'_id': turma})['alunos_ids']

    def test_aluno_criado_consegue_logar(self, client, professor, turma):
        professor.post('/api/students', json={
            'nome': 'Login OK', 'email': 'login@x.com',
            'senha': 'senha123', 'turma_id': str(turma),
        })
        r = client.post('/api/login', json={'email': 'login@x.com', 'senha': 'senha123'})
        assert r.status_code == 200
        assert r.get_json()['role'] == 'estudante'

    def test_lista_alunos_da_turma(self, professor, turma, estudante):
        r = professor.get('/api/teachers/all_students')
        assert r.status_code == 200
        assert r.get_json()['total'] == 1

    def test_edita_e_remove_aluno(self, professor, turma, estudante, db):
        assert professor.put(f'/api/students/{estudante.id}',
                             json={'nome': 'Nome Novo'}).status_code == 200
        assert db.users.find_one({'_id': estudante.oid})['nome'] == 'Nome Novo'

        assert professor.delete(f'/api/students/{estudante.id}').status_code == 200
        assert db.users.find_one({'_id': estudante.oid}) is None

    def test_ciclo_completo_de_avaliacao_e_nota(self, professor, turma, estudante):
        criacao = professor.post('/api/grades/assignments', json={
            'title': 'Prova 1', 'type': 'prova', 'class_id': str(turma),
            'subject': 'Matematica', 'max_score': 10,
        })
        assert criacao.status_code == 201
        assignment_id = criacao.get_json()['assignment_id']

        nota = professor.post('/api/grades/grades', json={
            'assignment_id': assignment_id, 'student_id': estudante.id, 'score': 8.5,
        })
        assert nota.status_code == 201

        consulta = professor.get(f'/api/grades/students/{estudante.id}/grades')
        assert consulta.get_json()['data'][0]['score'] == 8.5

    def test_nota_acima_do_maximo_e_rejeitada(self, professor, turma, estudante):
        criacao = professor.post('/api/grades/assignments', json={
            'title': 'P', 'type': 'prova', 'class_id': str(turma),
            'subject': 'Mat', 'max_score': 10,
        })
        r = professor.post('/api/grades/grades', json={
            'assignment_id': criacao.get_json()['assignment_id'],
            'student_id': estudante.id, 'score': 99,
        })
        assert r.status_code == 400

    def test_dashboard_consolida_turmas_e_alunos(self, professor, turma, estudante, alerta):
        r = professor.get('/api/teachers/dashboard')
        assert r.status_code == 200
        dados = r.get_json()['data']
        assert dados['total_turmas'] == 1
        assert dados['total_alunos'] == 1
        assert dados['alertas_ativos'] == 1

    def test_relatorio_da_turma(self, professor, turma):
        r = professor.get(f'/api/classes/{turma}/report')
        assert r.status_code == 200
        assert 'wellbeing' in r.get_json()['report']

    def test_cria_evento_na_agenda(self, professor, turma):
        r = professor.post('/api/schedule/events', json={
            'title': 'Prova de Matematica', 'type': 'prova', 'class_id': str(turma),
            'start_date': '2026-08-01T08:00:00Z', 'end_date': '2026-08-01T09:00:00Z',
        })
        assert r.status_code == 201
        assert len(professor.get('/api/schedule/events').get_json()['data']) == 1

    def test_cria_desafio_e_responde_pergunta(self, professor, turma, estudante):
        desafio = professor.post('/api/challenges', json={
            'title': 'Ler um livro', 'description': 'Leia 10 paginas',
            'class_id': str(turma),
        })
        assert desafio.status_code == 201

        pergunta = estudante.post('/api/qa/ask', json={
            'class_id': str(turma), 'question_text': 'Qual o prazo?',
        })
        assert pergunta.status_code == 201

        pendentes = professor.get('/api/qa/questions/professor').get_json()['data']
        assert len(pendentes) == 1

        resposta = professor.put(f'/api/qa/answer/{pendentes[0]["_id"]}',
                                 json={'answer_text': 'Ate sexta.'})
        assert resposta.status_code == 200


class TestFluxoEstudante:
    def test_registra_e_consulta_sentimento(self, estudante):
        r = estudante.post('/api/students/feelings',
                           json={'sentimento': 'feliz', 'emoji': ':)'})
        assert r.status_code == 201

        historico = estudante.get('/api/students/feelings')
        assert len(historico.get_json()['data']) == 1

    def test_professor_ve_o_sentimento_do_aluno(self, professor, turma, estudante):
        estudante.post('/api/students/feelings',
                       json={'sentimento': 'ansioso', 'emoji': ':|'})

        r = professor.get(f'/api/teachers/students/{estudante.id}/feelings')
        assert r.status_code == 200
        assert r.get_json()['data'][0]['sentimento'] == 'ansioso'

    def test_lista_e_completa_desafio(self, professor, turma, estudante):
        criacao = professor.post('/api/challenges', json={
            'title': 'Desafio', 'description': 'D', 'class_id': str(turma),
        })
        desafio_id = criacao.get_json()['challenge_id']

        ativos = estudante.get('/api/challenges/active')
        assert ativos.status_code == 200
        assert len(ativos.get_json()['data']) == 1

        assert estudante.post(f'/api/challenges/{desafio_id}/complete').status_code == 201

        depois = estudante.get('/api/challenges/active').get_json()['data']
        assert depois[0]['is_completed'] is True

    def test_nao_completa_o_mesmo_desafio_duas_vezes(self, professor, turma, estudante):
        criacao = professor.post('/api/challenges', json={
            'title': 'D', 'description': 'D', 'class_id': str(turma),
        })
        desafio_id = criacao.get_json()['challenge_id']

        estudante.post(f'/api/challenges/{desafio_id}/complete')
        segunda = estudante.post(f'/api/challenges/{desafio_id}/complete')
        assert segunda.status_code == 200

    def test_consulta_as_proprias_notas(self, professor, turma, estudante):
        criacao = professor.post('/api/grades/assignments', json={
            'title': 'P', 'type': 'prova', 'class_id': str(turma),
            'subject': 'Mat', 'max_score': 10,
        })
        professor.post('/api/grades/grades', json={
            'assignment_id': criacao.get_json()['assignment_id'],
            'student_id': estudante.id, 'score': 7.0,
        })

        r = estudante.get(f'/api/grades/students/{estudante.id}/grades')
        assert r.status_code == 200
        assert r.get_json()['data'][0]['score'] == 7.0

    def test_ve_eventos_da_propria_turma(self, professor, turma, estudante):
        professor.post('/api/schedule/events', json={
            'title': 'Aula', 'type': 'aula', 'class_id': str(turma),
            'start_date': '2026-08-01T08:00:00Z', 'end_date': '2026-08-01T09:00:00Z',
        })
        r = estudante.get('/api/schedule/events')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1

    def test_ve_as_proprias_turmas(self, estudante, turma):
        r = estudante.get('/api/classes')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1


class TestFluxoResponsavel:
    def test_vinculo_pedido_fica_pendente_ate_professor_confirmar(
        self, professor, turma, responsavel, estudante
    ):
        """Desde ADR-010: o vinculo nao da acesso sozinho — precisa de
        confirmacao de um professor da turma do aluno.
        """
        pedido = responsavel.post('/api/parents/link-child',
                                  json={'child_email': estudante.email})
        assert pedido.status_code == 202
        assert pedido.get_json()['vinculo_status'] == 'pendente'

        # Ainda pendente: o responsavel nao ve o filho.
        assert responsavel.get('/api/parents/children').get_json()['total'] == 0

        vinculo_id = pedido.get_json()['vinculo_id']
        confirmacao = professor.put(f'/api/teachers/link-requests/{vinculo_id}/confirm')
        assert confirmacao.status_code == 200

        # Confirmado: agora sim aparece.
        filhos = responsavel.get('/api/parents/children')
        assert filhos.get_json()['total'] == 1

    def test_professor_recusa_vinculo_indevido(self, professor, turma, responsavel, estudante):
        pedido = responsavel.post('/api/parents/link-child',
                                  json={'child_email': estudante.email})
        vinculo_id = pedido.get_json()['vinculo_id']

        recusa = professor.put(f'/api/teachers/link-requests/{vinculo_id}/reject')
        assert recusa.status_code == 200

        assert responsavel.get('/api/parents/children').get_json()['total'] == 0

    def test_pedir_vinculo_ja_confirmado_nao_duplica(
        self, professor, turma, responsavel, estudante
    ):
        primeiro = responsavel.post('/api/parents/link-child',
                                    json={'child_email': estudante.email})
        vinculo_id = primeiro.get_json()['vinculo_id']
        professor.put(f'/api/teachers/link-requests/{vinculo_id}/confirm')

        segundo = responsavel.post('/api/parents/link-child',
                                   json={'child_email': estudante.email})
        assert segundo.status_code == 200
        assert segundo.get_json()['vinculo_status'] == 'confirmado'

    def test_professor_ve_pedido_pendente_na_fila(self, professor, turma, responsavel, estudante):
        responsavel.post('/api/parents/link-child', json={'child_email': estudante.email})

        r = professor.get('/api/teachers/link-requests/pending')
        assert r.status_code == 200
        assert r.get_json()['total'] == 1
        assert r.get_json()['data'][0]['aluno_nome']
        assert r.get_json()['data'][0]['responsavel_email'] == responsavel.email

    def test_vinculo_falha_para_email_inexistente(self, responsavel):
        r = responsavel.post('/api/parents/link-child',
                             json={'child_email': 'ninguem@x.com'})
        assert r.status_code == 404

    def test_nao_vincula_um_professor_como_filho(self, responsavel, professor):
        r = responsavel.post('/api/parents/link-child',
                             json={'child_email': professor.email})
        assert r.status_code == 404

    def test_desvincula_filho(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.delete(f'/api/parents/unlink-child/{estudante.id}')
        assert r.status_code == 200
        assert vinculo_responsavel.get('/api/parents/children').get_json()['total'] == 0

    def test_acompanha_sentimentos_do_filho(self, vinculo_responsavel, estudante):
        estudante.post('/api/students/feelings',
                       json={'sentimento': 'calmo', 'emoji': ':)'})

        r = vinculo_responsavel.get(f'/api/parents/children/{estudante.id}/feelings')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1

    def test_ciclo_completo_do_kit_de_apoio(self, vinculo_responsavel, estudante):
        criacao = vinculo_responsavel.put(f'/api/support-kit/{estudante.id}', json={
            'interesses': ['dinossauros'],
            'sensibilidades': ['ruido alto'],
            'estrategias_calmantes': 'ambiente silencioso e fone abafador',
            'contatos_emergencia': [{'nome': 'Mae', 'telefone': '11999999999'}],
        })
        assert criacao.status_code == 200

        leitura = vinculo_responsavel.get(f'/api/support-kit/{estudante.id}')
        assert leitura.status_code == 200
        assert leitura.get_json()['data']['estrategias_calmantes'] == (
            'ambiente silencioso e fone abafador'
        )

    def test_kit_nao_aceita_nem_devolve_diagnostico(self, vinculo_responsavel, estudante):
        """ADR-003: o sistema nao armazena diagnostico.

        O kit tinha um campo 'neurodivergencia' de texto livre que guardava
        exatamente isso, era devolvido ao professor e — pior — ao proprio
        aluno, ja que pode_ver_aluno libera o proprio usuario. Este teste
        falha se o campo voltar por qualquer caminho.
        """
        vinculo_responsavel.put(f'/api/support-kit/{estudante.id}', json={
            'neurodivergencia': 'TEA nivel 1',
            'estrategias_calmantes': 'ambiente silencioso',
        })

        dados = vinculo_responsavel.get(
            f'/api/support-kit/{estudante.id}'
        ).get_json()['data']

        assert 'neurodivergencia' not in dados, (
            'REGRESSAO: campo de diagnostico voltou ao Kit de Apoio (ADR-003)'
        )

    def test_professor_da_turma_le_o_kit(self, professor, turma, vinculo_responsavel,
                                         estudante):
        """O professor precisa do kit para agir durante uma crise."""
        vinculo_responsavel.put(f'/api/support-kit/{estudante.id}',
                                json={'estrategias_calmantes': 'levar a sala de calma'})

        r = professor.get(f'/api/support-kit/{estudante.id}')
        assert r.status_code == 200
        assert 'sala de calma' in r.get_json()['data']['estrategias_calmantes']

    def test_cria_meta_para_o_filho(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.post('/api/students/goals', json={
            'student_id': estudante.id, 'title': 'Ler 10 min por dia',
            'description': 'Leitura diaria', 'deadline': '2026-12-31',
        })
        assert r.status_code == 201

        metas = vinculo_responsavel.get(f'/api/parents/children/{estudante.id}/goals')
        assert len(metas.get_json()['data']) == 1

    def test_dashboard_do_responsavel(self, vinculo_responsavel, estudante, alerta):
        r = vinculo_responsavel.get('/api/parents/dashboard')
        assert r.status_code == 200
        dados = r.get_json()['data']
        assert dados['total_filhos'] == 1
        assert dados['total_alertas_semana'] == 1


class TestComunicacao:
    def test_professor_e_responsavel_trocam_mensagens(self, professor, responsavel, turma, vinculo_responsavel):
        envio = professor.post('/api/messages', json={
            'to_user_id': responsavel.id, 'content': 'Bom dia, podemos conversar?',
        })
        assert envio.status_code == 201

        recebidas = responsavel.get('/api/messages').get_json()['data']
        assert len(recebidas) == 1
        assert recebidas[0]['direction'] == 'incoming'

    def test_nao_envia_para_o_mesmo_perfil(self, professor, outro_professor):
        r = professor.post('/api/messages',
                           json={'to_user_id': outro_professor.id, 'content': 'oi'})
        assert r.status_code == 403

    def test_nao_envia_sem_vinculo_comprovado(self, professor, responsavel):
        """Professor e responsavel sem nenhum aluno em comum nao podem se mensagear."""
        r = professor.post('/api/messages',
                           json={'to_user_id': responsavel.id, 'content': 'oi'})
        assert r.status_code == 403

    def test_marca_mensagem_como_lida(self, professor, responsavel, turma, vinculo_responsavel):
        envio = professor.post('/api/messages',
                               json={'to_user_id': responsavel.id, 'content': 'oi'})
        message_id = envio.get_json()['message_id']

        assert responsavel.put(f'/api/messages/{message_id}/read').status_code == 200
        assert responsavel.get('/api/messages/unread/count').get_json()['count'] == 0

    def test_mensagem_gera_notificacao(self, professor, responsavel, turma, vinculo_responsavel):
        professor.post('/api/messages',
                       json={'to_user_id': responsavel.id, 'content': 'oi'})

        r = responsavel.get('/api/notifications')
        assert r.status_code == 200
        assert r.get_json()['unread_count'] >= 1

    def test_forum_topico_e_resposta(self, professor, responsavel):
        criacao = professor.post('/api/forum/topics', json={
            'title': 'Rotina de sono', 'content': 'Como voces lidam?',
        })
        assert criacao.status_code == 201
        topic_id = criacao.get_json()['topic_id']

        resposta = responsavel.post(f'/api/forum/topics/{topic_id}/reply',
                                    json={'content': 'Aqui funcionou horario fixo.'})
        assert resposta.status_code == 201

        detalhe = professor.get(f'/api/forum/topics/{topic_id}').get_json()['data']
        assert detalhe['reply_count'] == 1

    def test_estudante_nao_cria_topico_mas_le(self, estudante, professor):
        professor.post('/api/forum/topics', json={'title': 'T', 'content': 'C'})

        assert estudante.get('/api/forum/topics').status_code == 200
        assert estudante.post('/api/forum/topics',
                              json={'title': 'X', 'content': 'Y'}).status_code == 403


class TestGaleria:
    def test_aluno_envia_professor_aprova_turma_ve(self, professor, turma, estudante):
        import io

        envio = estudante.post(
            '/api/gallery/upload',
            data={
                'file': (io.BytesIO(b'conteudo-de-teste'), 'desenho.png'),
                'class_id': str(turma),
                'title': 'Meu desenho',
            },
            content_type='multipart/form-data',
        )
        assert envio.status_code == 201
        creation_id = envio.get_json()['creation_id']

        # Antes da aprovacao, nao aparece na galeria da turma
        assert professor.get(f'/api/gallery/class/{turma}').get_json()['data'] == []

        pendentes = professor.get(f'/api/gallery/class/{turma}/pending')
        assert len(pendentes.get_json()['data']) == 1

        assert professor.put(
            f'/api/gallery/creation/{creation_id}/approve').status_code == 200

        aprovadas = professor.get(f'/api/gallery/class/{turma}').get_json()['data']
        assert len(aprovadas) == 1

    def test_rejeita_extensao_nao_permitida(self, turma, estudante):
        import io

        r = estudante.post(
            '/api/gallery/upload',
            data={
                'file': (io.BytesIO(b'MZ'), 'virus.exe'),
                'class_id': str(turma),
                'title': 'x',
            },
            content_type='multipart/form-data',
        )
        assert r.status_code == 400

    def test_arquivo_so_e_servido_a_quem_pode_ver_a_turma(self, professor, outro_professor, turma, estudante):
        import io

        envio = estudante.post(
            '/api/gallery/upload',
            data={
                'file': (io.BytesIO(b'conteudo-de-teste'), 'desenho.png'),
                'class_id': str(turma),
                'title': 'Desenho',
            },
            content_type='multipart/form-data',
        )
        assert envio.status_code == 201
        file_url = professor.get(
            f'/api/gallery/class/{turma}/pending'
        ).get_json()['data'][0]['file_url']

        assert estudante.get(file_url).status_code == 200
        assert professor.get(file_url).status_code == 200
        assert outro_professor.get(file_url).status_code == 403
