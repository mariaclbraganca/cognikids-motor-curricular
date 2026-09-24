"""Autenticacao, registro e perfil dos 3 tipos de usuario."""

import pytest


class TestRegistro:
    @pytest.mark.parametrize('tipo', ['estudante', 'professor', 'pai'])
    def test_registra_os_tres_perfis(self, client, tipo):
        r = client.post('/api/register', json={
            'nome': 'Fulano', 'email': f'{tipo}@x.com',
            'senha': 'senha123', 'tipo': tipo,
        })
        assert r.status_code == 201
        assert r.get_json()['user_id']

    def test_aceita_aluno_como_alias_de_estudante(self, client, db):
        """'aluno' e normalizado para o valor canonico 'estudante'."""
        r = client.post('/api/register', json={
            'nome': 'A', 'email': 'a@x.com', 'senha': 'senha123', 'tipo': 'aluno',
        })
        assert r.status_code == 201
        assert db.users.find_one({'email': 'a@x.com'})['tipo'] == 'estudante'

    def test_rejeita_tipo_invalido(self, client):
        r = client.post('/api/register', json={
            'nome': 'A', 'email': 'a@x.com', 'senha': 'senha123', 'tipo': 'hacker',
        })
        assert r.status_code == 400

    def test_rejeita_email_duplicado(self, client):
        dados = {'nome': 'A', 'email': 'dup@x.com', 'senha': 'senha123', 'tipo': 'professor'}
        assert client.post('/api/register', json=dados).status_code == 201
        assert client.post('/api/register', json=dados).status_code == 409

    def test_rejeita_email_invalido(self, client):
        r = client.post('/api/register', json={
            'nome': 'A', 'email': 'nao-e-email', 'senha': 'senha123', 'tipo': 'professor',
        })
        assert r.status_code == 400

    def test_rejeita_senha_curta(self, client):
        r = client.post('/api/register', json={
            'nome': 'A', 'email': 'a@x.com', 'senha': '123', 'tipo': 'professor',
        })
        assert r.status_code == 400

    def test_nao_armazena_senha_em_texto_claro(self, client, db):
        client.post('/api/register', json={
            'nome': 'A', 'email': 'h@x.com', 'senha': 'senha123', 'tipo': 'professor',
        })
        assert db.users.find_one({'email': 'h@x.com'})['senha'] != 'senha123'


class TestLogin:
    def test_login_valido_devolve_token(self, client, professor):
        r = client.post('/api/login', json={'email': professor.email, 'senha': 'senha123'})
        assert r.status_code == 200
        assert r.get_json()['token']

    def test_senha_errada_retorna_401(self, client, professor):
        r = client.post('/api/login', json={'email': professor.email, 'senha': 'errada'})
        assert r.status_code == 401

    def test_usuario_inexistente_retorna_401(self, client):
        r = client.post('/api/login', json={'email': 'nao@existe.com', 'senha': 'x'})
        assert r.status_code == 401

    def test_nao_revela_se_email_existe(self, client, professor):
        """Mensagem identica evita enumeracao de contas."""
        inexistente = client.post('/api/login', json={'email': 'no@x.com', 'senha': 'x'})
        senha_errada = client.post('/api/login', json={'email': professor.email, 'senha': 'x'})
        assert inexistente.get_json()['message'] == senha_errada.get_json()['message']


class TestProtecaoDeRotas:
    def test_sem_token_retorna_401(self, client):
        assert client.get('/api/profile').status_code == 401

    def test_token_invalido_retorna_401(self, client):
        r = client.get('/api/profile', headers={'Authorization': 'Bearer abc.def.ghi'})
        assert r.status_code == 401

    def test_token_assinado_com_outra_chave_retorna_401(self, client, professor):
        import jwt
        falso = jwt.encode(
            {'user_id': professor.id, 'exp': 9999999999}, 'chave-errada', algorithm='HS256'
        )
        r = client.get('/api/profile', headers={'Authorization': f'Bearer {falso}'})
        assert r.status_code == 401

    def test_token_expirado_retorna_401(self, client, professor, app):
        import datetime
        import jwt
        expirado = jwt.encode(
            {'user_id': professor.id,
             'exp': datetime.datetime.utcnow() - datetime.timedelta(hours=1)},
            app.config['SECRET_KEY'], algorithm='HS256',
        )
        r = client.get('/api/profile', headers={'Authorization': f'Bearer {expirado}'})
        assert r.status_code == 401

    def test_perfil_devolve_dados_do_usuario(self, professor):
        r = professor.get('/api/profile')
        assert r.status_code == 200
        assert r.get_json()['user']['tipo'] == 'professor'


class TestTrocaDeSenha:
    def test_troca_senha_com_senha_atual_correta(self, client, professor):
        r = professor.put('/api/change-password',
                          json={'senha_atual': 'senha123', 'senha_nova': 'novaSenha456'})
        assert r.status_code == 200

        assert client.post('/api/login', json={
            'email': professor.email, 'senha': 'novaSenha456'}).status_code == 200

    def test_rejeita_senha_atual_errada(self, professor):
        r = professor.put('/api/change-password',
                          json={'senha_atual': 'errada', 'senha_nova': 'novaSenha456'})
        assert r.status_code == 401


class TestStatus:
    def test_api_status_existe(self, client):
        """Endpoint citado no README, antes ausente."""
        assert client.get('/api/status').status_code in (200, 503)

    def test_status_existe(self, client):
        assert client.get('/status').status_code in (200, 503)

    def test_rota_inexistente_devolve_json(self, client):
        r = client.get('/api/rota-que-nao-existe')
        assert r.status_code == 404
        assert r.get_json()['status'] == 'erro'
