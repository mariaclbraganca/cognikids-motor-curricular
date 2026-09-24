"""
Endpoints de avaliacoes e notas.

Professor cria avaliacoes e lanca notas nas proprias turmas; aluno ve as
proprias notas; responsavel ve as notas dos filhos.
"""

import logging

from flask import Blueprint, request

from app.Models.class_model import Class
from app.Models.grade_model import Grade
from app.Models.user_model import User
from app.Utils.authz import pode_editar_turma, pode_ver_aluno, pode_ver_turma, to_object_id
from app.Utils.decorators import professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

grade_blueprint = Blueprint('grade', __name__)
grade_model = Grade()
class_model = Class()
user_model = User()


@grade_blueprint.route('/assignments', methods=['POST'])
@token_required
@professor_required
def create_assignment(current_user):
    """Cria uma avaliacao numa turma do professor."""
    try:
        data = request.get_json(silent=True) or {}
        obrigatorios = ['title', 'type', 'class_id', 'subject', 'max_score']
        faltando = [c for c in obrigatorios if data.get(c) is None]
        if faltando:
            return dados_invalidos(f'Campos obrigatorios em falta: {", ".join(faltando)}')

        turma = class_model.get_class_by_id(data['class_id'])
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        data['created_by'] = current_user['_id']
        resultado = grade_model.create_assignment(data)

        return sucesso(
            message='Avaliacao criada com sucesso!',
            status_code=201,
            assignment_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao criar avaliacao')


@grade_blueprint.route('/classes/<class_id>/assignments', methods=['GET'])
@token_required
def get_class_assignments(current_user, class_id):
    """Lista as avaliacoes de uma turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Acesso nao autorizado a esta turma')

        avaliacoes = grade_model.get_class_assignments(class_id)
        serializadas = [Grade.serializar_avaliacao(a) for a in avaliacoes]

        return sucesso(data=serializadas, dados=serializadas)

    except Exception as e:
        return erro_interno(e, 'ao listar avaliacoes')


@grade_blueprint.route('/assignments/<assignment_id>', methods=['PUT'])
@token_required
@professor_required
def update_assignment(current_user, assignment_id):
    """Atualiza uma avaliacao."""
    try:
        avaliacao = grade_model.get_assignment_by_id(assignment_id)
        if not avaliacao:
            return nao_encontrado('Avaliacao nao encontrada')

        turma = class_model.get_class_by_id(avaliacao['class_id'])
        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        resultado = grade_model.update_assignment(
            assignment_id, request.get_json(silent=True) or {}
        )
        if resultado is None:
            return dados_invalidos('Nenhum campo valido para atualizar')

        return sucesso(message='Avaliacao atualizada com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao atualizar avaliacao')


@grade_blueprint.route('/assignments/<assignment_id>', methods=['DELETE'])
@token_required
@professor_required
def delete_assignment(current_user, assignment_id):
    """Desativa uma avaliacao."""
    try:
        avaliacao = grade_model.get_assignment_by_id(assignment_id)
        if not avaliacao:
            return nao_encontrado('Avaliacao nao encontrada')

        turma = class_model.get_class_by_id(avaliacao['class_id'])
        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        grade_model.delete_assignment(assignment_id)
        return sucesso(message='Avaliacao removida com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover avaliacao')


@grade_blueprint.route('/grades', methods=['POST'])
@token_required
@professor_required
def submit_grade(current_user):
    """Lanca a nota de um aluno numa avaliacao."""
    try:
        data = request.get_json(silent=True) or {}
        obrigatorios = ['assignment_id', 'student_id', 'score']
        faltando = [c for c in obrigatorios if data.get(c) is None]
        if faltando:
            return dados_invalidos(f'Campos obrigatorios em falta: {", ".join(faltando)}')

        avaliacao = grade_model.get_assignment_by_id(data['assignment_id'])
        if not avaliacao:
            return nao_encontrado('Avaliacao nao encontrada')

        turma = class_model.get_class_by_id(avaliacao['class_id'])
        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        aluno_oid = to_object_id(data['student_id'])
        if aluno_oid is None:
            return dados_invalidos('student_id invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Aluno nao pertence as suas turmas')

        try:
            score = float(data['score'])
        except (TypeError, ValueError):
            return dados_invalidos('score deve ser numerico')

        max_score = avaliacao.get('max_score')
        if max_score is not None and not (0 <= score <= float(max_score)):
            return dados_invalidos(f'score deve estar entre 0 e {max_score}')

        resultado = grade_model.submit_grade({
            'assignment_id': data['assignment_id'],
            'student_id': aluno_oid,
            'class_id': avaliacao['class_id'],
            'score': score,
            'feedback': data.get('feedback', ''),
            'comments': data.get('comments', ''),
            'is_absent': data.get('is_absent', False),
            'graded_by': current_user['_id'],
        })

        return sucesso(
            message='Nota lancada com sucesso!',
            status_code=201,
            grade_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao lancar nota')


@grade_blueprint.route('/students/<student_id>/grades', methods=['GET'])
@token_required
def get_student_grades(current_user, student_id):
    """Notas de um aluno (proprio, professor da turma ou responsavel)."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado as notas deste aluno')

        class_id = request.args.get('class_id')
        notas = grade_model.get_student_grades(str(aluno_oid), class_id)

        return sucesso(data=[Grade.serializar_nota(n) for n in notas])

    except Exception as e:
        return erro_interno(e, 'ao buscar notas do aluno')


@grade_blueprint.route('/grades/<grade_id>', methods=['PUT'])
@token_required
@professor_required
def update_grade(current_user, grade_id):
    """Corrige uma nota lancada."""
    try:
        nota = grade_model.get_grade_by_id(grade_id)
        if not nota:
            return nao_encontrado('Nota nao encontrada')

        turma = class_model.get_class_by_id(nota['class_id'])
        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        data = request.get_json(silent=True) or {}
        permitidos = {'score', 'feedback', 'comments', 'is_absent'}
        atualizacao = {k: v for k, v in data.items() if k in permitidos}

        if not atualizacao:
            return dados_invalidos('Nenhum campo valido para atualizar')

        if 'score' in atualizacao:
            try:
                atualizacao['score'] = float(atualizacao['score'])
            except (TypeError, ValueError):
                return dados_invalidos('score deve ser numerico')

        grade_model.update_grade(grade_id, atualizacao)
        return sucesso(message='Nota atualizada com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao atualizar nota')


@grade_blueprint.route('/students/<student_id>/average', methods=['GET'])
@token_required
def get_student_average(current_user, student_id):
    """Media ponderada de um aluno numa turma."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado as notas deste aluno')

        class_id = request.args.get('class_id')
        if not class_id:
            return dados_invalidos('O parametro class_id e obrigatorio')

        media = grade_model.calculate_student_average(str(aluno_oid), class_id)
        return sucesso(data={'average': media, 'student_id': str(aluno_oid)})

    except Exception as e:
        return erro_interno(e, 'ao calcular media do aluno')
