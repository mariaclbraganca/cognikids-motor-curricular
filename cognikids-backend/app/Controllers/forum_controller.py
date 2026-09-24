# app/Controllers/forum_controller.py
"""
Forum de discussao da comunidade escolar.

Todos os perfis autenticados leem e respondem; professores e responsaveis
criam topicos. O autor (ou um professor) pode editar e remover.
"""

import logging

from flask import Blueprint, request

from app.Models.forum_model import ForumModel
from app.Utils.decorators import roles_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)
from app.Utils.roles import ADMIN, PROFESSOR, RESPONSAVEL, normalizar_tipo

logger = logging.getLogger(__name__)

forum_blueprint = Blueprint('forum_bp', __name__)
forum_model = ForumModel()


def _pode_gerir_topico(current_user, topico):
    """Autor do topico, professor ou admin podem editar/remover."""
    if str(topico.get('author_id')) == str(current_user['_id']):
        return True
    return normalizar_tipo(current_user.get('tipo')) in (PROFESSOR, ADMIN)


@forum_blueprint.route('/forum/topics', methods=['GET'])
@token_required
def get_all_topics(current_user):
    """Lista os topicos do forum."""
    try:
        categoria = request.args.get('categoria')
        if categoria:
            topicos = forum_model.get_topics_by_category(categoria)
        else:
            topicos = forum_model.get_all_topics()

        return sucesso(data=[ForumModel.serializar(t) for t in topicos])

    except Exception as e:
        return erro_interno(e, 'ao listar topicos do forum')


@forum_blueprint.route('/forum/topics/<string:topic_id>', methods=['GET'])
@token_required
def get_topic(current_user, topic_id):
    """Detalhes de um topico com as suas respostas."""
    try:
        topico = forum_model.get_topic_by_id(topic_id)
        if not topico or not topico.get('is_active', True):
            return nao_encontrado('Topico nao encontrado')

        return sucesso(data=ForumModel.serializar(topico))

    except Exception as e:
        return erro_interno(e, 'ao buscar topico')


@forum_blueprint.route('/forum/topics', methods=['POST'])
@token_required
@roles_required(PROFESSOR, RESPONSAVEL, ADMIN)
def create_topic(current_user):
    """Cria um topico (professores e responsaveis)."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('title') or not data.get('content'):
            return dados_invalidos('Titulo e conteudo sao obrigatorios')

        resultado = forum_model.create_topic({
            'title': data['title'],
            'content': data['content'],
            'author_id': current_user['_id'],
            'author_name': current_user.get('nome', ''),
            'author_type': normalizar_tipo(current_user.get('tipo')),
            'category': data.get('category'),
        })

        return sucesso(
            message='Topico criado com sucesso!',
            status_code=201,
            topic_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao criar topico')


@forum_blueprint.route('/forum/topics/<string:topic_id>/reply', methods=['POST'])
@token_required
def add_reply_to_topic(current_user, topic_id):
    """Adiciona uma resposta a um topico."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('content'):
            return dados_invalidos('Conteudo da resposta e obrigatorio')

        topico = forum_model.get_topic_by_id(topic_id)
        if not topico or not topico.get('is_active', True):
            return nao_encontrado('Topico nao encontrado')

        forum_model.add_reply(topic_id, {
            'content': data['content'],
            'author_id': current_user['_id'],
            'author_name': current_user.get('nome', ''),
            'author_type': normalizar_tipo(current_user.get('tipo')),
        })

        return sucesso(message='Resposta adicionada com sucesso!', status_code=201)

    except Exception as e:
        return erro_interno(e, 'ao responder topico')


@forum_blueprint.route('/forum/topics/<string:topic_id>', methods=['PUT'])
@token_required
def update_topic(current_user, topic_id):
    """Edita um topico (autor, professor ou admin)."""
    try:
        topico = forum_model.get_topic_by_id(topic_id)
        if not topico or not topico.get('is_active', True):
            return nao_encontrado('Topico nao encontrado')

        if not _pode_gerir_topico(current_user, topico):
            return nao_autorizado('Apenas o autor pode editar este topico')

        data = request.get_json(silent=True) or {}
        permitidos = {'title', 'content', 'category'}
        atualizacao = {k: v for k, v in data.items() if k in permitidos}

        resultado = forum_model.update_topic(topic_id, atualizacao)
        if resultado is None:
            return dados_invalidos('Nenhum campo valido para atualizar')

        return sucesso(message='Topico atualizado com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao atualizar topico')


@forum_blueprint.route('/forum/topics/<string:topic_id>', methods=['DELETE'])
@token_required
def delete_topic(current_user, topic_id):
    """Remove um topico (autor, professor ou admin)."""
    try:
        topico = forum_model.get_topic_by_id(topic_id)
        if not topico or not topico.get('is_active', True):
            return nao_encontrado('Topico nao encontrado')

        if not _pode_gerir_topico(current_user, topico):
            return nao_autorizado('Apenas o autor pode remover este topico')

        forum_model.delete_topic(topic_id)
        return sucesso(message='Topico removido com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover topico')
