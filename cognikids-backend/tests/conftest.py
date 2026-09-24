"""
Fixtures compartilhadas da suite de testes do CogniKids.

Os testes rodam contra um MongoDB real quando disponivel (variavel
TEST_MONGO_URI ou o Mongo padrao em localhost) e caem para mongomock caso
contrario, de modo que a suite roda em qualquer maquina sem infraestrutura.
"""

import datetime
import os
import sys

import pytest
from bson.objectid import ObjectId

# Garante que o pacote 'app' seja importavel ao rodar pytest da raiz
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEST_SECRET = 'chave-de-teste-com-tamanho-suficiente-1234567890'
TEST_API_KEY = 'api-key-de-teste'
TEST_DB = 'cognikids_test'


def _mongo_uri_disponivel():
    """Retorna uma URI de Mongo real utilizavel, ou None."""
    uri = os.getenv('TEST_MONGO_URI', f'mongodb://localhost:27017/{TEST_DB}')
    try:
        from pymongo import MongoClient

        MongoClient(uri, serverSelectionTimeoutMS=800).admin.command('ping')
        return uri
    except Exception:
        return None


@pytest.fixture(scope='session')
def mongo_uri():
    uri = _mongo_uri_disponivel()
    if uri:
        return uri

    # Sem Mongo real: usa mongomock via patch do PyMongo
    pytest.importorskip('mongomock')
    return f'mongodb://localhost:27017/{TEST_DB}'


@pytest.fixture(scope='session')
def _usar_mongomock():
    return _mongo_uri_disponivel() is None


@pytest.fixture
def app(mongo_uri, _usar_mongomock, monkeypatch):
    """Instancia da aplicacao Flask configurada para testes."""
    os.environ['MONGO_URI'] = mongo_uri
    os.environ['SECRET_KEY'] = TEST_SECRET
    os.environ['SECRET_API_KEY'] = TEST_API_KEY
    os.environ['FLASK_DEBUG'] = '0'

    if _usar_mongomock:
        import mongomock
        from flask_pymongo import PyMongo

        cliente = mongomock.MongoClient()

        def _fake_init_app(self, app_, *args, **kwargs):
            self.cx = cliente
            self.db = cliente[TEST_DB]

        monkeypatch.setattr(PyMongo, 'init_app', _fake_init_app, raising=False)

    from app import create_app

    aplicacao = create_app({'TESTING': True})

    with aplicacao.app_context():
        from app import mongo

        # Base limpa a cada teste
        for colecao in mongo.db.list_collection_names():
            mongo.db[colecao].delete_many({})

        yield aplicacao


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from app import mongo

    return mongo.db


# --------------------------------------------------------------------------
# Helpers de criacao de usuarios e vinculos
# --------------------------------------------------------------------------

class Ator:
    """Um usuario autenticado pronto para fazer requisicoes."""

    def __init__(self, client, user_id, token, tipo, email):
        self._client = client
        self.id = user_id
        self.oid = ObjectId(user_id)
        self.token = token
        self.tipo = tipo
        self.email = email

    @property
    def headers(self):
        return {'Authorization': f'Bearer {self.token}'}

    def get(self, url, **kw):
        return self._client.get(url, headers=self.headers, **kw)

    def post(self, url, **kw):
        return self._client.post(url, headers=self.headers, **kw)

    def put(self, url, **kw):
        return self._client.put(url, headers=self.headers, **kw)

    def delete(self, url, **kw):
        return self._client.delete(url, headers=self.headers, **kw)


@pytest.fixture
def criar_usuario(client):
    """Registra e autentica um usuario, devolvendo um Ator."""

    contador = {'n': 0}

    def _criar(tipo, nome=None, email=None, senha='senha123'):
        contador['n'] += 1
        email = email or f'{tipo}{contador["n"]}@cognikids.test'
        nome = nome or f'{tipo.capitalize()} {contador["n"]}'

        resposta = client.post('/api/register', json={
            'nome': nome, 'email': email, 'senha': senha, 'tipo': tipo,
        })
        assert resposta.status_code == 201, resposta.get_data(as_text=True)

        login = client.post('/api/login', json={'email': email, 'senha': senha})
        assert login.status_code == 200, login.get_data(as_text=True)

        corpo = login.get_json()
        return Ator(client, corpo['user']['id'], corpo['token'], tipo, email)

    return _criar


@pytest.fixture
def professor(criar_usuario):
    return criar_usuario('professor')


@pytest.fixture
def outro_professor(criar_usuario):
    """Professor sem nenhum vinculo com a turma do fixture `turma`."""
    return criar_usuario('professor')


@pytest.fixture
def estudante(criar_usuario):
    return criar_usuario('estudante')


@pytest.fixture
def responsavel(criar_usuario):
    return criar_usuario('pai')


def _conceder_consentimento(db, aluno_oid, autor_oid=None, **finalidades):
    """Grava consentimento diretamente, sem passar pela API.

    Usado pelas fixtures para montar o cenario padrao (tudo autorizado), de
    modo que os testes de funcionalidade nao precisem repetir o fluxo de
    consentimento a cada caso.
    """
    padrao = {
        'uso_app': True,
        'coleta_biometrica': True,
        'compartilhar_escola': True,
        'uso_pesquisa': False,
    }
    padrao.update(finalidades)

    db.consents.update_one(
        {'aluno_id': aluno_oid},
        {'$set': {
            'aluno_id': aluno_oid,
            'finalidades': padrao,
            'versao_termo': '1.0.0',
            'atualizado_em': datetime.datetime.utcnow(),
            'atualizado_por': autor_oid or aluno_oid,
        }},
        upsert=True,
    )
    return padrao


@pytest.fixture
def conceder_consentimento(db):
    """Helper para os testes ajustarem o consentimento de um aluno."""
    def _conceder(aluno, **finalidades):
        oid = aluno.oid if hasattr(aluno, 'oid') else ObjectId(str(aluno))
        return _conceder_consentimento(db, oid, **finalidades)

    return _conceder


@pytest.fixture
def turma(db, professor, estudante):
    """Turma do `professor` com o `estudante` matriculado.

    Ja inclui o consentimento do responsavel: sem ele o professor nao
    enxerga o aluno, e o objetivo desta fixture e o cenario pedagogico
    normal. Os testes de consentimento montam seus proprios cenarios.
    """
    turma_id = db.turmas.insert_one({
        'name': 'Turma Teste',
        'grade': '3o Ano',
        'section': 'A',
        'school_year': '2026',
        'teacher_id': professor.oid,
        'alunos_ids': [estudante.oid],
        'subjects': [],
        'is_active': True,
        'created_at': datetime.datetime.utcnow(),
    }).inserted_id

    db.users.update_one({'_id': professor.oid}, {'$set': {'turmas_ids': [turma_id]}})
    db.users.update_one({'_id': estudante.oid}, {'$set': {'turma_id': turma_id}})

    _conceder_consentimento(db, estudante.oid)

    return turma_id


@pytest.fixture
def vinculo_responsavel(db, responsavel, estudante):
    """Vincula o `responsavel` ao `estudante`."""
    db.users.update_one(
        {'_id': responsavel.oid}, {'$set': {'filhos_ids': [estudante.oid]}}
    )
    return responsavel


@pytest.fixture
def alerta(db, estudante):
    """Um alerta de crise gravado no formato do alert_monitor."""
    return db.alerts.insert_one({
        'aluno_id': estudante.oid,
        'data_hora': datetime.datetime.utcnow(),
        'dados_biometricos': {'bpm': 155, 'gsr': 4.8, 'movement_score': 2.1},
        'severity': 'high',
        'motivo': 'Predicao do Modelo de ML',
        'ml_confidence': 0.91,
        'resolvido': False,
    }).inserted_id


@pytest.fixture
def dispositivo(db, estudante):
    """Pulseira do estudante, com consentimento biometrico ja concedido.

    Sem o consentimento a ingestao e rejeitada por falta de base legal —
    comportamento verificado especificamente em test_consentimento.py.
    """
    _conceder_consentimento(db, estudante.oid)

    return db.dispositivos.insert_one({
        'aluno_id': estudante.oid,
        'status': 'ativo',
        'ultima_conexao': None,
    }).inserted_id


@pytest.fixture
def api_key_headers():
    return {'X-API-Key': TEST_API_KEY}
