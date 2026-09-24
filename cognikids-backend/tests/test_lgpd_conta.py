"""Recuperacao de senha, portabilidade e exclusao de conta (LGPD art. 18)."""

import datetime

import pytest


class TestRecuperacaoSenha:
    def _pedir_token(self, client, email, monkeypatch):
        capturado = {}
        monkeypatch.setattr(
            'app.Controllers.auth_controller.enviar_email_recuperacao',
            lambda destinatario, token, validade_minutos: capturado.update(token=token),
        )
        client.post('/api/forgot-password', json={'email': email})
        return capturado.get('token')

    def test_email_existente_cria_token_sem_vazar_na_resposta(self, client, professor, db, monkeypatch):
        capturado = {}
        monkeypatch.setattr(
            'app.Controllers.auth_controller.enviar_email_recuperacao',
            lambda destinatario, token, validade_minutos: capturado.update(
                destinatario=destinatario, token=token
            ),
        )

        r = client.post('/api/forgot-password', json={'email': professor.email})
        assert r.status_code == 200
        assert 'token' not in r.get_data(as_text=True)
        assert capturado['destinatario'] == professor.email
        assert db.password_resets.count_documents({'user_id': professor.oid}) == 1

    def test_email_inexistente_devolve_mesma_mensagem(self, client, professor, monkeypatch):
        monkeypatch.setattr(
            'app.Controllers.auth_controller.enviar_email_recuperacao', lambda *a, **k: True
        )
        existente = client.post('/api/forgot-password', json={'email': professor.email})
        inexistente = client.post('/api/forgot-password', json={'email': 'ninguem@x.com'})
        assert existente.status_code == inexistente.status_code == 200
        assert existente.get_json()['message'] == inexistente.get_json()['message']

    def test_sem_email_retorna_400(self, client):
        assert client.post('/api/forgot-password', json={}).status_code == 400

    def test_sem_smtp_configurado_a_rota_continua_segura(self, client, professor, monkeypatch):
        """Sem EMAIL_SMTP_HOST (fallback de log real, sem monkeypatch do
        envio), a rota nao falha e nao vaza o token na resposta."""
        monkeypatch.delenv('EMAIL_SMTP_HOST', raising=False)
        r = client.post('/api/forgot-password', json={'email': professor.email})
        assert r.status_code == 200
        assert 'token' not in r.get_data(as_text=True)

    def test_reset_com_token_valido_troca_a_senha(self, client, professor, monkeypatch):
        token = self._pedir_token(client, professor.email, monkeypatch)

        r = client.post('/api/reset-password', json={'token': token, 'senha_nova': 'novaSenha456'})
        assert r.status_code == 200

        login = client.post('/api/login', json={'email': professor.email, 'senha': 'novaSenha456'})
        assert login.status_code == 200

    def test_reset_com_token_invalido_retorna_400(self, client):
        r = client.post(
            '/api/reset-password',
            json={'token': 'token-que-nao-existe', 'senha_nova': 'novaSenha456'},
        )
        assert r.status_code == 400

    def test_reset_nao_permite_reutilizar_o_token(self, client, professor, monkeypatch):
        token = self._pedir_token(client, professor.email, monkeypatch)
        primeira = client.post('/api/reset-password', json={'token': token, 'senha_nova': 'novaSenha456'})
        segunda = client.post('/api/reset-password', json={'token': token, 'senha_nova': 'outraSenha789'})
        assert primeira.status_code == 200
        assert segunda.status_code == 400

    def test_novo_pedido_invalida_o_token_anterior(self, client, professor, monkeypatch):
        token_antigo = self._pedir_token(client, professor.email, monkeypatch)
        self._pedir_token(client, professor.email, monkeypatch)

        r = client.post('/api/reset-password', json={'token': token_antigo, 'senha_nova': 'novaSenha456'})
        assert r.status_code == 400

    def test_reset_rejeita_senha_curta(self, client, professor, monkeypatch):
        token = self._pedir_token(client, professor.email, monkeypatch)
        r = client.post('/api/reset-password', json={'token': token, 'senha_nova': '123'})
        assert r.status_code == 400

    def test_reset_expirado_retorna_400(self, client, professor, db, monkeypatch):
        token = self._pedir_token(client, professor.email, monkeypatch)
        db.password_resets.update_many(
            {'user_id': professor.oid},
            {'$set': {'expira_em': datetime.datetime.utcnow() - datetime.timedelta(minutes=1)}},
        )
        r = client.post('/api/reset-password', json={'token': token, 'senha_nova': 'novaSenha456'})
        assert r.status_code == 400


class TestExportacaoDados:
    def test_requer_autenticacao(self, client):
        assert client.get('/api/me/export').status_code == 401

    def test_estudante_inclui_categorias_e_omite_senha(self, estudante, db, alerta, dispositivo):
        db.feelings.insert_one({
            'aluno_id': estudante.oid, 'sentimento': 'feliz',
            'data_hora': datetime.datetime.utcnow(),
        })

        r = estudante.get('/api/me/export')
        assert r.status_code == 200
        dados = r.get_json()['data']

        assert dados['perfil']['email'] == estudante.email
        assert 'senha' not in dados['perfil']
        assert len(dados['alertas']) == 1
        assert len(dados['dispositivos']) == 1
        assert len(dados['sentimentos']) == 1

    def test_responsavel_inclui_vinculos_pedidos(self, responsavel, estudante, db):
        db.vinculos_pendentes.insert_one({
            'responsavel_id': responsavel.oid, 'aluno_id': estudante.oid,
            'status': 'pendente', 'criado_em': datetime.datetime.utcnow(),
            'confirmado_por': None, 'confirmado_em': None,
        })

        r = responsavel.get('/api/me/export')
        assert r.status_code == 200
        assert len(r.get_json()['data']['vinculos_pedidos']) == 1

    def test_professor_inclui_turmas(self, professor, turma):
        r = professor.get('/api/me/export')
        assert r.status_code == 200
        assert len(r.get_json()['data']['turmas']) == 1


class TestExclusaoDeConta:
    def test_exige_senha_correta(self, estudante):
        r = estudante.delete('/api/me', json={'senha': 'errada'})
        assert r.status_code == 401

    def test_exclui_usuario_e_dados_sensiveis_do_estudante(self, estudante, db, alerta, dispositivo):
        r = estudante.delete('/api/me', json={'senha': 'senha123'})
        assert r.status_code == 200
        assert db.users.find_one({'_id': estudante.oid}) is None
        assert db.alerts.count_documents({'aluno_id': estudante.oid}) == 0
        assert db.dispositivos.count_documents({'aluno_id': estudante.oid}) == 0

    def test_exclusao_do_aluno_desvincula_do_responsavel(self, estudante, vinculo_responsavel, db):
        estudante.delete('/api/me', json={'senha': 'senha123'})
        responsavel_doc = db.users.find_one({'_id': vinculo_responsavel.oid})
        assert estudante.oid not in responsavel_doc.get('filhos_ids', [])

    def test_exclusao_do_aluno_remove_da_turma(self, estudante, turma, db):
        estudante.delete('/api/me', json={'senha': 'senha123'})
        turma_doc = db.turmas.find_one({'_id': turma})
        assert estudante.oid not in turma_doc.get('alunos_ids', [])

    def test_professor_com_turma_nao_pode_se_excluir(self, professor, turma):
        r = professor.delete('/api/me', json={'senha': 'senha123'})
        assert r.status_code == 409

    def test_professor_sem_turma_pode_se_excluir(self, outro_professor, db):
        r = outro_professor.delete('/api/me', json={'senha': 'senha123'})
        assert r.status_code == 200
        assert db.users.find_one({'_id': outro_professor.oid}) is None

    def test_responsavel_pode_se_excluir_sem_apagar_o_filho(self, responsavel, vinculo_responsavel, estudante, db):
        r = responsavel.delete('/api/me', json={'senha': 'senha123'})
        assert r.status_code == 200
        assert db.users.find_one({'_id': estudante.oid}) is not None

    def test_conta_excluida_nao_consegue_mais_logar(self, estudante):
        estudante.delete('/api/me', json={'senha': 'senha123'})
        r = estudante._client.post(
            '/api/login', json={'email': estudante.email, 'senha': 'senha123'}
        )
        assert r.status_code == 401
