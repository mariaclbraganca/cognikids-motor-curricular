"""
Endpoints de turmas.

Toda rota de escrita valida que o usuario e o professor titular da turma.
Antes, qualquer professor autenticado conseguia renomear ou desativar a
turma de outro professor apenas conhecendo o seu ID.
"""

import logging

from flask import Blueprint, request

from app import mongo
from app.Models.class_model import Class
from app.Models.feeling_model import Feeling
from app.Models.grade_model import Grade
from app.Models.user_model import User
from app.Utils.authz import (
    filhos_do_responsavel,
    pode_editar_turma,
    pode_ver_aluno,
    pode_ver_turma,
    to_object_id,
)
from app.Utils.decorators import professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)
from app.Utils.roles import ESTUDANTE, PROFESSOR, RESPONSAVEL, ADMIN, normalizar_tipo

logger = logging.getLogger(__name__)

class_blueprint = Blueprint('class', __name__)
class_model = Class()
grade_model = Grade()
feeling_model = Feeling()
user_model = User()


def _serializar_turma(turma):
    alunos = turma.get('alunos_ids') or turma.get('students') or []
    created_at = turma.get('created_at')
    return {
        '_id': str(turma.get('_id')),
        'name': turma.get('name') or turma.get('nome', 'Sem Nome'),
        'grade': turma.get('grade', ''),
        'section': turma.get('section', ''),
        'school_year': turma.get('school_year', ''),
        'subjects': turma.get('subjects', []),
        'teacher_id': str(turma.get('teacher_id')) if turma.get('teacher_id') else None,
        'student_count': len(alunos),
        'is_active': turma.get('is_active', True),
        'created_at': created_at.isoformat() if created_at else None,
    }


@class_blueprint.route('', methods=['GET'])
@token_required
def get_classes(current_user):
    """Lista as turmas visiveis ao usuario, conforme o seu perfil."""
    try:
        tipo = normalizar_tipo(current_user.get('tipo'))

        if tipo in (PROFESSOR, ADMIN):
            turmas = class_model.get_teacher_classes(str(current_user['_id']))
        elif tipo == ESTUDANTE:
            turmas = class_model.get_student_classes(str(current_user['_id']))
        elif tipo == RESPONSAVEL:
            turmas = class_model.get_parent_classes(filhos_do_responsavel(current_user))
        else:
            turmas = []

        return sucesso(data=[_serializar_turma(t) for t in turmas])

    except Exception as e:
        return erro_interno(e, 'ao listar turmas')


@class_blueprint.route('/<string:class_id>', methods=['GET'])
@token_required
def get_class_details(current_user, class_id):
    """Detalhes de uma turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Acesso nao autorizado a esta turma')

        return sucesso(data=_serializar_turma(turma))

    except Exception as e:
        return erro_interno(e, 'ao buscar turma')


@class_blueprint.route('/<string:class_id>/students', methods=['GET'])
@token_required
def get_class_students(current_user, class_id):
    """Alunos matriculados na turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Acesso nao autorizado a esta turma')

        ids = class_model.get_class_students(class_id)
        alunos = []
        for aluno in user_model.find_students_by_ids(ids):
            aluno['_id'] = str(aluno['_id'])
            if aluno.get('turma_id'):
                aluno['turma_id'] = str(aluno['turma_id'])
            alunos.append(aluno)

        return sucesso(data=alunos, total=len(alunos))

    except Exception as e:
        return erro_interno(e, 'ao listar alunos da turma')


@class_blueprint.route('/<string:class_id>/report', methods=['GET'])
@token_required
def get_class_report(current_user, class_id):
    """Relatorio de desempenho e bem-estar da turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Acesso nao autorizado a esta turma')

        alunos_ids = class_model.get_class_students(class_id)
        feelings = feeling_model.find_feelings_by_aluno_ids(
            [str(a) for a in alunos_ids]
        ) if alunos_ids else []

        contagem = {}
        for f in feelings:
            sentimento = f.get('sentimento') or 'unknown'
            contagem[sentimento] = contagem.get(sentimento, 0) + 1

        return sucesso(report={
            'class_id': str(turma['_id']),
            'name': turma.get('name'),
            'wellbeing': {'total_records': len(feelings), 'counts': contagem},
            'grades_summary': grade_model.get_class_grades_summary(class_id),
            'student_count': len(alunos_ids),
        })

    except Exception as e:
        return erro_interno(e, 'ao gerar relatorio da turma')


@class_blueprint.route('', methods=['POST'])
@class_blueprint.route('/classes', methods=['POST'])
@token_required
@professor_required
def create_class(current_user):
    """Cria uma turma com o professor logado como titular."""
    try:
        data = request.get_json(silent=True) or {}

        if not (data.get('name') or data.get('nome')):
            return dados_invalidos('O nome da turma e obrigatorio')

        # O titular e sempre o usuario autenticado: aceitar teacher_id do
        # corpo permitiria criar turmas em nome de outro professor.
        data['teacher_id'] = current_user['_id']

        resultado = class_model.create_class(data)
        user_model.add_class_to_teacher(current_user['_id'], resultado.inserted_id)

        return sucesso(
            message='Turma criada com sucesso',
            status_code=201,
            _id=str(resultado.inserted_id),
            class_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao criar turma')


@class_blueprint.route('/<string:class_id>', methods=['PUT'])
@class_blueprint.route('/classes/<string:class_id>', methods=['PUT'])
@token_required
@professor_required
def update_class(current_user, class_id):
    """Atualiza a turma (apenas o titular)."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        resultado = class_model.update_class(class_id, request.get_json(silent=True) or {})
        if resultado is None:
            return dados_invalidos('Nenhum campo valido para atualizar')

        return sucesso(message='Turma atualizada')

    except Exception as e:
        return erro_interno(e, 'ao atualizar turma')


@class_blueprint.route('/<string:class_id>', methods=['DELETE'])
@class_blueprint.route('/classes/<string:class_id>', methods=['DELETE'])
@token_required
@professor_required
def delete_class(current_user, class_id):
    """Desativa a turma (apenas o titular)."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        class_model.deactivate_class(class_id)
        user_model.remove_class_from_teacher(current_user['_id'], class_id)

        return sucesso(message='Turma removida')

    except Exception as e:
        return erro_interno(e, 'ao remover turma')


@class_blueprint.route('/<string:class_id>/enroll_student', methods=['POST'])
@token_required
@professor_required
def enroll_student(current_user, class_id):
    """Matricula um aluno na turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        data = request.get_json(silent=True) or {}
        aluno_oid = to_object_id(data.get('student_id'))
        if aluno_oid is None:
            return dados_invalidos('ID do aluno obrigatorio e valido')

        aluno = user_model.find_user_by_id(aluno_oid)
        if not aluno:
            return nao_encontrado('Aluno nao encontrado')

        if normalizar_tipo(aluno.get('tipo')) != ESTUDANTE:
            return dados_invalidos('O usuario informado nao e um estudante')

        class_model.enroll_student(class_id, aluno_oid)
        user_model.update_user(aluno_oid, {'turma_id': to_object_id(class_id)})

        return sucesso(message='Aluno matriculado')

    except Exception as e:
        return erro_interno(e, 'ao matricular aluno')


@class_blueprint.route('/<string:class_id>/remove_student', methods=['POST'])
@token_required
@professor_required
def remove_student(current_user, class_id):
    """Remove um aluno da turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        data = request.get_json(silent=True) or {}
        aluno_oid = to_object_id(data.get('student_id'))
        if aluno_oid is None:
            return dados_invalidos('ID do aluno obrigatorio e valido')

        class_model.remove_student(class_id, aluno_oid)

        # So limpa o vinculo reverso se ele apontava para esta turma
        aluno = user_model.find_user_by_id(aluno_oid)
        if aluno and str(aluno.get('turma_id')) == str(class_id):
            mongo.db.users.update_one(
                {'_id': aluno_oid}, {'$set': {'turma_id': None}}
            )

        return sucesso(message='Aluno removido')

    except Exception as e:
        return erro_interno(e, 'ao remover aluno da turma')
