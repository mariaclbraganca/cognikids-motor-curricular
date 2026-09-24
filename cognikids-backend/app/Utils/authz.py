"""
Regras de autorizacao do CogniKids.

Centraliza as respostas a pergunta "este usuario pode acessar os dados deste
aluno / desta turma?". Antes essa logica estava espalhada (e ausente) pelos
controllers, o que permitia a um professor ler e alterar dados de turmas de
outro professor.

Os dados em questao sao biometricos e de menores neurodivergentes, entao a
regra e sempre negar por padrao: so libera quando o vinculo e comprovado.
"""

from bson.objectid import ObjectId
from bson.errors import InvalidId

from app import mongo
from app.Utils.roles import (
    normalizar_tipo,
    variacoes_de,
    ESTUDANTE,
    PROFESSOR,
    RESPONSAVEL,
    ADMIN,
)


def to_object_id(valor):
    """Converte para ObjectId, retornando None se invalido."""
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        return None


def ids_iguais(a, b):
    """Compara dois identificadores que podem ser str ou ObjectId."""
    if a is None or b is None:
        return False
    return str(a) == str(b)


def turmas_do_professor(professor):
    """ObjectIds das turmas que o professor leciona.

    Combina a lista desnormalizada em users.turmas_ids com a fonte de
    verdade (turmas.teacher_id), porque as duas podem divergir conforme o
    caminho usado para criar a turma.
    """
    ids = set()

    for turma_id in professor.get('turmas_ids', []) or []:
        oid = to_object_id(turma_id)
        if oid:
            ids.add(oid)

    professor_oid = to_object_id(professor.get('_id'))
    if professor_oid:
        for turma in mongo.db.turmas.find({'teacher_id': professor_oid}, {'_id': 1}):
            ids.add(turma['_id'])

    return ids


def alunos_do_professor(professor):
    """ObjectIds de todos os alunos das turmas do professor."""
    turmas_ids = turmas_do_professor(professor)
    if not turmas_ids:
        return set()

    alunos = set()

    # Alunos referenciados pela turma
    for turma in mongo.db.turmas.find({'_id': {'$in': list(turmas_ids)}},
                                      {'alunos_ids': 1, 'students': 1}):
        for campo in ('alunos_ids', 'students'):
            for aluno_id in turma.get(campo, []) or []:
                oid = to_object_id(aluno_id)
                if oid:
                    alunos.add(oid)

    # Alunos que apontam para a turma (vinculo reverso)
    for aluno in mongo.db.users.find(
        {
            'tipo': {'$in': variacoes_de(ESTUDANTE)},
            'turma_id': {'$in': list(turmas_ids)},
        },
        {'_id': 1},
    ):
        alunos.add(aluno['_id'])

    return alunos


def filhos_do_responsavel(responsavel):
    """ObjectIds dos filhos vinculados ao responsavel."""
    ids = set()
    for filho_id in responsavel.get('filhos_ids', []) or []:
        oid = to_object_id(filho_id)
        if oid:
            ids.add(oid)
    return ids


def pode_ver_aluno(current_user, aluno_id):
    """O usuario pode ver os dados deste aluno?

    - admin: sim
    - o proprio aluno: sim
    - professor: se o aluno esta em uma de suas turmas E o responsavel
      autorizou o compartilhamento com a escola
    - responsavel: apenas se o aluno for seu filho

    O vinculo pedagogico nao basta para o professor: sem consentimento do
    responsavel nao ha base legal para o tratamento dos dados da crianca.
    """
    aluno_oid = to_object_id(aluno_id)
    if aluno_oid is None:
        return False

    tipo = normalizar_tipo(current_user.get('tipo'))

    if tipo == ADMIN:
        return True

    if ids_iguais(current_user.get('_id'), aluno_oid):
        return True

    if tipo == PROFESSOR:
        from app.Models.consent_model import COMPARTILHAR_ESCOLA

        if aluno_oid not in alunos_do_professor(current_user):
            return False
        return consentimento_permite(aluno_oid, COMPARTILHAR_ESCOLA)

    if tipo == RESPONSAVEL:
        return aluno_oid in filhos_do_responsavel(current_user)

    return False


def pode_editar_aluno(current_user, aluno_id):
    """Somente professor da turma do aluno (ou admin) pode editar/remover.

    Gestao de cadastro (matricula, dados escolares) depende do vinculo
    pedagogico, nao do consentimento de compartilhamento de dados: um
    responsavel que revoga o consentimento nao deixa a crianca fora da
    turma, apenas impede o professor de ver seus dados sensiveis.
    """
    tipo = normalizar_tipo(current_user.get('tipo'))

    if tipo == ADMIN:
        return True

    if tipo == PROFESSOR:
        aluno_oid = to_object_id(aluno_id)
        return aluno_oid is not None and aluno_oid in alunos_do_professor(current_user)

    return False


def pode_ver_turma(current_user, turma):
    """O usuario pode ver esta turma?

    Aceita o documento da turma ja carregado para evitar consulta redundante.
    """
    if not turma:
        return False

    tipo = normalizar_tipo(current_user.get('tipo'))

    if tipo == ADMIN:
        return True

    if tipo == PROFESSOR:
        return ids_iguais(turma.get('teacher_id'), current_user.get('_id'))

    turma_oid = to_object_id(turma.get('_id'))

    if tipo == ESTUDANTE:
        if ids_iguais(current_user.get('turma_id'), turma_oid):
            return True
        proprio = to_object_id(current_user.get('_id'))
        matriculados = [to_object_id(a) for a in
                        (turma.get('alunos_ids', []) or []) + (turma.get('students', []) or [])]
        return proprio in matriculados

    if tipo == RESPONSAVEL:
        filhos = filhos_do_responsavel(current_user)
        if not filhos:
            return False
        matriculados = {to_object_id(a) for a in
                        (turma.get('alunos_ids', []) or []) + (turma.get('students', []) or [])}
        if filhos & matriculados:
            return True
        return mongo.db.users.count_documents(
            {'_id': {'$in': list(filhos)}, 'turma_id': turma_oid}
        ) > 0

    return False


def pode_editar_turma(current_user, turma):
    """Somente o professor titular da turma (ou admin) pode alterar/excluir."""
    if not turma:
        return False

    tipo = normalizar_tipo(current_user.get('tipo'))

    if tipo == ADMIN:
        return True

    if tipo == PROFESSOR:
        return ids_iguais(turma.get('teacher_id'), current_user.get('_id'))

    return False


def alunos_visiveis(current_user):
    """Conjunto de ObjectIds de alunos que o usuario pode ver.

    Usado nos endpoints de listagem (alertas, sentimentos) para restringir a
    consulta no proprio banco, em vez de filtrar depois.

    Para o professor, aplica tambem o consentimento: alunos cujo responsavel
    nao autorizou o compartilhamento com a escola nao aparecem.
    """
    tipo = normalizar_tipo(current_user.get('tipo'))

    if tipo == ADMIN:
        return {u['_id'] for u in mongo.db.users.find(
            {'tipo': {'$in': variacoes_de(ESTUDANTE)}}, {'_id': 1}
        )}

    if tipo == PROFESSOR:
        return filtrar_por_consentimento(alunos_do_professor(current_user))

    if tipo == RESPONSAVEL:
        return filhos_do_responsavel(current_user)

    if tipo == ESTUDANTE:
        proprio = to_object_id(current_user.get('_id'))
        return {proprio} if proprio else set()

    return set()


def pode_enviar_mensagem(remetente, destinatario):
    """Existe vinculo pedagogico/familiar comprovado entre os dois usuarios?

    Os dois canais suportados sao professor<->responsavel e professor<->aluno
    (ver message_controller.py). Sem isso, qualquer professor autenticado
    podia mandar mensagem direta para qualquer aluno do sistema, mesmo fora
    de suas turmas — corrigido aqui, reaproveitando as mesmas regras de
    vinculo+consentimento ja usadas para leitura de dados do aluno.
    """
    tipo_remetente = normalizar_tipo(remetente.get('tipo'))
    tipo_destinatario = normalizar_tipo(destinatario.get('tipo'))

    if tipo_remetente == PROFESSOR:
        professor, outro = remetente, destinatario
    elif tipo_destinatario == PROFESSOR:
        professor, outro = destinatario, remetente
    else:
        return False

    tipo_outro = normalizar_tipo(outro.get('tipo'))

    if tipo_outro == ESTUDANTE:
        return pode_ver_aluno(professor, outro.get('_id'))

    if tipo_outro == RESPONSAVEL:
        comuns = filhos_do_responsavel(outro) & alunos_do_professor(professor)
        if not comuns:
            return False
        from app.Models.consent_model import COMPARTILHAR_ESCOLA
        return any(consentimento_permite(filho_id, COMPARTILHAR_ESCOLA) for filho_id in comuns)

    return False


def consentimento_permite(aluno_id, finalidade):
    """Ha consentimento vigente desta finalidade para este aluno?

    Import local evita ciclo: consent_model importa de app, que importa os
    controllers, que importam este modulo.
    """
    from app.Models.consent_model import Consent

    return Consent().permite(aluno_id, finalidade)


def filtrar_por_consentimento(alunos_ids, finalidade=None):
    """Mantem apenas os alunos com consentimento para a finalidade.

    Sem consentimento de compartilhamento com a escola, o aluno nao aparece
    em nenhuma listagem do professor.
    """
    from app.Models.consent_model import COMPARTILHAR_ESCOLA, Consent

    finalidade = finalidade or COMPARTILHAR_ESCOLA
    modelo = Consent()

    return {
        aluno_id for aluno_id in alunos_ids
        if modelo.permite(aluno_id, finalidade)
    }
