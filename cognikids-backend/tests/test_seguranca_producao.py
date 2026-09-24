"""Testes que TENTAM o ataque. Se algum passar, o build deve quebrar.

Diferente do resto da suite, que verifica se a funcionalidade funciona,
aqui cada teste encena uma exploracao real encontrada em auditoria e falha
se ela voltar a ser possivel. E o unico mecanismo que impede a regressao de
uma falha de seguranca ja corrigida.
"""

from bson.objectid import ObjectId


# --------------------------------------------------------------------------
# Escalonamento de privilegio pelo cadastro publico
# --------------------------------------------------------------------------

def test_registro_publico_recusa_admin(client):
    """POST /api/register e rota publica (sem token).

    Aceitar tipo='admin' do corpo permitia que qualquer pessoa com acesso de
    rede a API criasse para si um perfil que ignora consentimento em
    pode_ver_aluno e alunos_visiveis — ou seja, leitura de biometria,
    alertas, sentimentos, notas e perfil funcional de TODAS as criancas.
    """
    resposta = client.post('/api/register', json={
        'nome': 'Invasor',
        'email': 'invasor@exemplo.test',
        'senha': 'senha123',
        'tipo': 'admin',
    })

    assert resposta.status_code != 201, (
        'REGRESSAO CRITICA: o cadastro publico voltou a criar admin'
    )
    assert resposta.status_code == 400


def test_registro_publico_recusa_alias_de_admin(client):
    """normalizar_tipo mapeia 'administrador' -> 'admin' (Utils/roles.py).

    Bloquear so a string exata 'admin' deixaria a porta aberta pelo alias.
    """
    resposta = client.post('/api/register', json={
        'nome': 'Invasor',
        'email': 'invasor2@exemplo.test',
        'senha': 'senha123',
        'tipo': 'administrador',
    })

    assert resposta.status_code == 400


def test_registro_publico_nao_grava_usuario_admin(client, db):
    """Nao basta responder 400: nada pode ter sido gravado."""
    client.post('/api/register', json={
        'nome': 'Invasor',
        'email': 'invasor3@exemplo.test',
        'senha': 'senha123',
        'tipo': 'admin',
    })

    assert db.users.find_one({'email': 'invasor3@exemplo.test'}) is None


def test_registro_publico_aceita_perfis_legitimos(client):
    """A correcao nao pode ter fechado o cadastro normal."""
    for indice, tipo in enumerate(('estudante', 'professor', 'pai')):
        resposta = client.post('/api/register', json={
            'nome': f'Usuario {tipo}',
            'email': f'legitimo{indice}@exemplo.test',
            'senha': 'senha123',
            'tipo': tipo,
        })
        assert resposta.status_code == 201, (
            f'cadastro legitimo de {tipo} quebrou: {resposta.get_data(as_text=True)}'
        )


# --------------------------------------------------------------------------
# link-child sem confirmacao de terceiro (ADR-010)
# --------------------------------------------------------------------------

def test_desconhecido_nao_ganha_acesso_so_vinculando(client, estudante):
    """Antes desta correcao, era exatamente isto: cadastro publico como
    'pai' + e-mail do aluno = acesso imediato a biometria e alertas dela.
    """
    client.post('/api/register', json={
        'nome': 'Estranho', 'email': 'estranho@exemplo.test',
        'senha': 'senha123', 'tipo': 'pai',
    })
    login = client.post('/api/login', json={
        'email': 'estranho@exemplo.test', 'senha': 'senha123',
    })
    token = login.get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}

    pedido = client.post('/api/parents/link-child', headers=headers,
                         json={'child_email': estudante.email})
    assert pedido.status_code == 202, (
        'REGRESSAO CRITICA: link-child voltou a vincular sem confirmacao'
    )

    filhos = client.get('/api/parents/children', headers=headers)
    assert filhos.get_json()['total'] == 0, (
        'REGRESSAO CRITICA: estranho ganhou acesso ao aluno sem confirmacao da escola'
    )


def test_professor_sem_a_turma_nao_confirma_vinculo_alheio(
    outro_professor, professor, turma, responsavel, estudante
):
    """So um professor de UMA turma do aluno pode confirmar — nao qualquer professor."""
    pedido = responsavel.post('/api/parents/link-child',
                              json={'child_email': estudante.email})
    vinculo_id = pedido.get_json()['vinculo_id']

    resposta = outro_professor.put(f'/api/teachers/link-requests/{vinculo_id}/confirm')
    assert resposta.status_code == 404, (
        'REGRESSAO CRITICA: professor sem vinculo com a turma confirmou vinculo alheio'
    )

    assert responsavel.get('/api/parents/children').get_json()['total'] == 0


def test_professor_sem_a_turma_nao_ve_pedido_na_fila(
    outro_professor, professor, turma, responsavel, estudante
):
    responsavel.post('/api/parents/link-child', json={'child_email': estudante.email})

    r = outro_professor.get('/api/teachers/link-requests/pending')
    assert r.status_code == 200
    assert r.get_json()['total'] == 0


def test_admin_enxerga_aluno_sem_consentimento(app, estudante):
    """Documenta POR QUE admin nunca pode nascer de rota publica.

    Este teste afirma o comportamento atual — admin e' bypass incondicional
    de consentimento (Utils/authz.py). Nao e' um bug a corrigir aqui: e' a
    razao pela qual o perfil so pode ser criado por quem tem acesso ao
    servidor (scripts/criar_admin.py). Se algum dia o bypass for removido,
    este teste falha e obriga a revisar a decisao conscientemente.
    """
    from app.Utils.authz import alunos_visiveis

    admin = {'_id': ObjectId(), 'tipo': 'admin'}

    # O estudante nao tem nenhum consentimento gravado.
    assert estudante.oid in alunos_visiveis(admin)
