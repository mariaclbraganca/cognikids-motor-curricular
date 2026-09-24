"""
Endpoints do perfil Estudante e a gestao de alunos feita pelo professor.
"""

import datetime
import logging

from flask import Blueprint, request

from app import bcrypt, mongo
from app.Models.class_model import Class
from app.Models.feeling_model import Feeling
from app.Models.goal_model import Goal
from app.Models.user_model import User
from app.Utils.authz import pode_editar_aluno, pode_ver_aluno, to_object_id
from app.Utils.decorators import estudante_required, professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)
from app.Utils.roles import ESTUDANTE, PROFESSOR, RESPONSAVEL, normalizar_tipo
from app.Utils.validators import validate_email

logger = logging.getLogger(__name__)

student_blueprint = Blueprint('student', __name__)
feeling_model = Feeling()
goal_model = Goal()
user_model = User()
class_model = Class()

SENHA_MIN_LEN = 6


@student_blueprint.route('', methods=['POST'])
@token_required
@professor_required
def create_student(current_user):
    """Cria um estudante e o associa a uma turma do professor."""
    try:
        data = request.get_json(silent=True) or {}

        obrigatorios = ['nome', 'email', 'senha', 'turma_id']
        faltando = [c for c in obrigatorios if not data.get(c)]
        if faltando:
            return dados_invalidos(
                f'Campos obrigatorios em falta: {", ".join(faltando)}'
            )

        email = data['email'].strip().lower()
        if not validate_email(email):
            return dados_invalidos('Email invalido')

        if len(data['senha']) < SENHA_MIN_LEN:
            return dados_invalidos(
                f'A senha deve ter pelo menos {SENHA_MIN_LEN} caracteres'
            )

        turma_oid = to_object_id(data['turma_id'])
        if turma_oid is None:
            return dados_invalidos('turma_id invalido')

        turma = class_model.get_class_by_id(turma_oid)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        # O professor so pode criar alunos nas proprias turmas
        from app.Utils.authz import pode_editar_turma
        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        if user_model.find_user_by_email(email):
            return erro('Este e-mail ja esta em uso', 409)

        resultado = user_model.create_user({
            'nome': data['nome'].strip(),
            'email': email,
            'senha': bcrypt.generate_password_hash(data['senha']).decode('utf-8'),
            'tipo': ESTUDANTE,
            'turma_id': turma_oid,
        })

        if not resultado.get('success'):
            return erro(resultado.get('message', 'Erro ao criar aluno'), 500)

        student_id = resultado['user_id']
        class_model.add_student_to_class(turma_oid, student_id)

        return sucesso(
            message='Aluno criado e associado a turma com sucesso!',
            status_code=201,
            student_id=student_id,
        )

    except Exception as e:
        return erro_interno(e, 'ao criar aluno')


@student_blueprint.route('/feelings', methods=['POST'])
@token_required
@estudante_required
def add_feeling(current_user):
    """Registra o sentimento do proprio aluno."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('sentimento') or not data.get('emoji'):
            return dados_invalidos('Dados em falta: sentimento e emoji sao obrigatorios')

        resultado = feeling_model.create_feeling({
            'aluno_id': str(current_user['_id']),
            'sentimento': data['sentimento'],
            'emoji': data['emoji'],
            'descricao': data.get('descricao'),
        })

        return sucesso(
            message='Sentimento registado com sucesso!',
            status_code=201,
            feeling_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao registrar sentimento')


@student_blueprint.route('/feelings', methods=['GET'])
@token_required
@estudante_required
def get_my_feelings(current_user):
    """Historico de sentimentos do proprio aluno."""
    try:
        feelings = feeling_model.find_feelings_by_aluno_id(str(current_user['_id']))
        for f in feelings:
            f['_id'] = str(f['_id'])
            f['aluno_id'] = str(f['aluno_id'])
            if f.get('timestamp'):
                f['timestamp'] = f['timestamp'].isoformat()
        return sucesso(data=feelings)

    except Exception as e:
        return erro_interno(e, 'ao buscar sentimentos')


@student_blueprint.route('/<string:student_id>/goals', methods=['GET'])
@token_required
def get_student_goals(current_user, student_id):
    """Metas de um aluno. Visivel ao proprio, ao professor da turma e ao responsavel."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado as metas deste aluno')

        goals = goal_model.find_by_student_id(aluno_oid)
        return sucesso(data=[Goal.serializar(g) for g in goals])

    except Exception as e:
        return erro_interno(e, 'ao buscar metas')


@student_blueprint.route('/goals', methods=['POST'])
@token_required
def create_student_goal(current_user):
    """Cria uma meta para um aluno (professor da turma ou responsavel)."""
    try:
        if normalizar_tipo(current_user.get('tipo')) not in (PROFESSOR, RESPONSAVEL):
            return nao_autorizado('Apenas professores ou responsaveis podem criar metas')

        data = request.get_json(silent=True) or {}
        obrigatorios = ['student_id', 'title', 'description', 'deadline']
        faltando = [c for c in obrigatorios if not data.get(c)]
        if faltando:
            return dados_invalidos(
                f'Campos obrigatorios em falta: {", ".join(faltando)}'
            )

        aluno_oid = to_object_id(data['student_id'])
        if aluno_oid is None:
            return dados_invalidos('student_id invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado a este aluno')

        resultado = goal_model.create_goal({
            'student_id': aluno_oid,
            'title': data['title'],
            'description': data['description'],
            'deadline': data['deadline'],
            'created_by': current_user['_id'],
            'progress': data.get('progress', 0),
            'status': data.get('status', 'current'),
        })

        return sucesso(
            message='Meta criada com sucesso!',
            status_code=201,
            goal_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao criar meta')


@student_blueprint.route('/goals/<string:goal_id>', methods=['PUT'])
@token_required
def update_student_goal(current_user, goal_id):
    """Atualiza uma meta (professor/responsavel vinculado, ou o proprio aluno)."""
    try:
        meta = goal_model.find_by_id(goal_id)
        if not meta:
            return nao_encontrado('Meta nao encontrada')

        if not pode_ver_aluno(current_user, meta.get('student_id')):
            return nao_autorizado('Acesso nao autorizado a esta meta')

        data = request.get_json(silent=True) or {}
        permitidos = {'title', 'description', 'deadline', 'progress', 'status'}
        atualizacao = {k: v for k, v in data.items() if k in permitidos}

        if not atualizacao:
            return dados_invalidos('Nenhum campo valido para atualizar')

        goal_model.update_goal(goal_id, atualizacao)
        return sucesso(message='Meta atualizada com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao atualizar meta')


@student_blueprint.route('/goals/<string:goal_id>', methods=['DELETE'])
@token_required
def delete_student_goal(current_user, goal_id):
    """Remove uma meta (apenas professor da turma ou responsavel)."""
    try:
        meta = goal_model.find_by_id(goal_id)
        if not meta:
            return nao_encontrado('Meta nao encontrada')

        if normalizar_tipo(current_user.get('tipo')) not in (PROFESSOR, RESPONSAVEL):
            return nao_autorizado('Apenas professores ou responsaveis podem remover metas')

        if not pode_ver_aluno(current_user, meta.get('student_id')):
            return nao_autorizado('Acesso nao autorizado a esta meta')

        goal_model.delete_goal(goal_id)
        return sucesso(message='Meta removida com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover meta')


@student_blueprint.route('/<string:student_id>', methods=['GET'])
@token_required
def get_student(current_user, student_id):
    """Dados de um aluno."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado a este aluno')

        aluno = user_model.find_public_by_id(aluno_oid)
        if not aluno:
            return nao_encontrado('Aluno nao encontrado')

        aluno['_id'] = str(aluno['_id'])
        if aluno.get('turma_id'):
            aluno['turma_id'] = str(aluno['turma_id'])

        return sucesso(data=aluno)

    except Exception as e:
        return erro_interno(e, 'ao buscar aluno')


@student_blueprint.route('/<string:student_id>', methods=['PUT'])
@token_required
@professor_required
def update_student(current_user, student_id):
    """Atualiza os dados de um estudante (professor da turma)."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        aluno = user_model.find_user_by_id(aluno_oid)
        if not aluno:
            return nao_encontrado('Aluno nao encontrado')

        if not pode_editar_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso negado: nao e professor deste aluno')

        data = request.get_json(silent=True) or {}
        atualizacao = {}

        if data.get('nome'):
            atualizacao['nome'] = data['nome'].strip()

        if data.get('email'):
            email = data['email'].strip().lower()
            if not validate_email(email):
                return dados_invalidos('Email invalido')
            existente = user_model.find_user_by_email(email)
            if existente and str(existente['_id']) != str(aluno_oid):
                return erro('Email ja registado por outro usuario', 409)
            atualizacao['email'] = email

        if data.get('turma_id'):
            turma_oid = to_object_id(data['turma_id'])
            if turma_oid is None:
                return dados_invalidos('turma_id invalido')

            from app.Utils.authz import pode_editar_turma
            turma_destino = class_model.get_class_by_id(turma_oid)
            if not turma_destino:
                return nao_encontrado('Turma de destino nao encontrada')
            if not pode_editar_turma(current_user, turma_destino):
                return nao_autorizado('Acesso negado: nao e professor da turma de destino')

            atualizacao['turma_id'] = turma_oid

        if not atualizacao:
            return dados_invalidos('Nenhum campo valido para atualizar')

        user_model.update_user(aluno_oid, atualizacao)

        # Mantem a matricula da turma coerente com o vinculo do aluno
        if 'turma_id' in atualizacao:
            if aluno.get('turma_id'):
                class_model.remove_student(aluno['turma_id'], aluno_oid)
            class_model.enroll_student(atualizacao['turma_id'], aluno_oid)

        return sucesso(message='Dados do aluno atualizados com sucesso!')

    except Exception as e:
        return erro_interno(e, 'ao atualizar aluno')


@student_blueprint.route('/<string:student_id>', methods=['DELETE'])
@token_required
@professor_required
def delete_student(current_user, student_id):
    """Remove um estudante e limpa seus vinculos."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        aluno = user_model.find_user_by_id(aluno_oid)
        if not aluno:
            return nao_encontrado('Aluno nao encontrado')

        if not pode_editar_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso negado: nao e professor deste aluno')

        if aluno.get('turma_id'):
            class_model.remove_student(aluno['turma_id'], aluno_oid)

        # Remove o aluno da lista de filhos de qualquer responsavel
        mongo.db.users.update_many(
            {'filhos_ids': aluno_oid}, {'$pull': {'filhos_ids': aluno_oid}}
        )

        user_model.delete_user(aluno_oid)

        return sucesso(message='Aluno removido com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover aluno')
