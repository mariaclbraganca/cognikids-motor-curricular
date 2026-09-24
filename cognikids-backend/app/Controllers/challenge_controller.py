# app/Controllers/challenge_controller.py
"""
Desafios propostos aos alunos.

Professor cria/edita desafios nas proprias turmas; aluno lista os ativos e
marca conclusao.
"""

import logging

from flask import Blueprint, request

from app.Models.challenge_model import ChallengeModel
from app.Models.class_model import Class
from app.Utils.authz import pode_editar_turma, pode_ver_turma
from app.Utils.decorators import estudante_required, professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

challenge_blueprint = Blueprint('challenge_bp', __name__)
challenge_model = ChallengeModel()
class_model = Class()


def _autorizar_turma_do_desafio(current_user, desafio):
    """Confere se o professor pode gerir o desafio.

    Desafios sem turma associada ficam restritos ao seu criador.
    """
    class_id = desafio.get('class_id')
    if class_id:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return False
        return pode_editar_turma(current_user, turma)

    return str(desafio.get('created_by')) == str(current_user['_id'])


@challenge_blueprint.route('/active', methods=['GET'])
@challenge_blueprint.route('/challenges/active', methods=['GET'])
@token_required
@estudante_required
def get_active_challenges(current_user):
    """(ALUNO) Lista os desafios ativos e marca os ja concluidos."""
    try:
        challenges = challenge_model.get_active_challenges()
        completions = challenge_model.get_student_completions(str(current_user['_id']))
        concluidos = {str(c['challenge_id']) for c in completions}

        data = [
            {
                '_id': str(c['_id']),
                'title': c.get('title'),
                'description': c.get('description'),
                'points': c.get('points', 0),
                'class_id': str(c['class_id']) if c.get('class_id') else None,
                'is_completed': str(c['_id']) in concluidos,
            }
            for c in challenges
        ]

        return sucesso(data=data)

    except Exception as e:
        return erro_interno(e, 'ao listar desafios ativos')


@challenge_blueprint.route('/<string:challenge_id>/complete', methods=['POST'])
@challenge_blueprint.route('/challenges/<string:challenge_id>/complete', methods=['POST'])
@token_required
@estudante_required
def complete_challenge(current_user, challenge_id):
    """(ALUNO) Marca um desafio como concluido."""
    try:
        desafio = challenge_model.get_challenge_by_id(challenge_id)
        if not desafio or not desafio.get('is_active'):
            return nao_encontrado('Desafio nao encontrado ou nao esta mais ativo')

        resultado = challenge_model.complete_challenge(
            str(current_user['_id']), challenge_id
        )

        if resultado is None:
            return sucesso(message='Voce ja completou este desafio!')

        return sucesso(
            message=f"Parabens! Desafio '{desafio['title']}' concluido com sucesso!",
            status_code=201,
        )

    except Exception as e:
        return erro_interno(e, 'ao concluir desafio')


@challenge_blueprint.route('', methods=['POST'])
@challenge_blueprint.route('/challenges', methods=['POST'])
@token_required
@professor_required
def create_challenge(current_user):
    """(PROFESSOR) Cria um novo desafio."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('title') or not data.get('description'):
            return dados_invalidos('Titulo e descricao sao obrigatorios')

        # Quando ha turma, o professor precisa ser o titular
        if data.get('class_id'):
            turma = class_model.get_class_by_id(data['class_id'])
            if not turma:
                return nao_encontrado('Turma nao encontrada')
            if not pode_editar_turma(current_user, turma):
                return nao_autorizado('Acesso negado: nao e professor desta turma')

        data['created_by'] = str(current_user['_id'])
        resultado = challenge_model.create_challenge(data)

        return sucesso(
            message='Desafio criado com sucesso!',
            status_code=201,
            challenge_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao criar desafio')


@challenge_blueprint.route('/<string:challenge_id>', methods=['PUT'])
@token_required
@professor_required
def update_challenge(current_user, challenge_id):
    """(PROFESSOR) Atualiza um desafio."""
    try:
        desafio = challenge_model.get_challenge_by_id(challenge_id)
        if not desafio:
            return nao_encontrado('Desafio nao encontrado')

        if not _autorizar_turma_do_desafio(current_user, desafio):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        data = request.get_json(silent=True) or {}
        permitidos = {'title', 'description', 'points', 'is_active', 'dueDate', 'due_date'}
        atualizacao = {k: v for k, v in data.items() if k in permitidos}

        if not atualizacao:
            return dados_invalidos('Nenhum campo valido para atualizar')

        resultado = challenge_model.update_challenge(challenge_id, atualizacao)
        if resultado is None or resultado.matched_count == 0:
            return nao_encontrado('Desafio nao encontrado para atualizar')

        return sucesso(message='Desafio atualizado com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao atualizar desafio')


@challenge_blueprint.route('/<string:challenge_id>', methods=['DELETE'])
@token_required
@professor_required
def delete_challenge(current_user, challenge_id):
    """(PROFESSOR) Remove um desafio."""
    try:
        desafio = challenge_model.get_challenge_by_id(challenge_id)
        if not desafio:
            return nao_encontrado('Desafio nao encontrado')

        if not _autorizar_turma_do_desafio(current_user, desafio):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        challenge_model.delete_challenge(challenge_id)
        return sucesso(message='Desafio removido com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover desafio')