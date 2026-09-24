"""
Mensagens diretas entre usuarios de perfis diferentes
(professor <-> responsavel, professor <-> aluno).
"""

import logging

from flask import Blueprint, request

from app.Models.message_model import Message
from app.Models.user_model import User
from app.Utils.authz import pode_enviar_mensagem, to_object_id
from app.Utils.decorators import token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)
from app.Utils.roles import ADMIN, normalizar_tipo

logger = logging.getLogger(__name__)

message_blueprint = Blueprint('message_bp', __name__)
message_model = Message()
user_model = User()

CONTEUDO_MAX = 5000


def _serializar(msg, current_user_id, nomes=None):
    direcao = 'outgoing' if str(msg['from_user_id']) == str(current_user_id) else 'incoming'
    outro_id = msg['to_user_id'] if direcao == 'outgoing' else msg['from_user_id']

    dados = {
        '_id': str(msg['_id']),
        'from_user_id': str(msg['from_user_id']),
        'to_user_id': str(msg['to_user_id']),
        'content': msg['content'],
        'type': msg.get('type', 'text'),
        'priority': msg.get('priority', 'normal'),
        'timestamp': msg['timestamp'].isoformat() if msg.get('timestamp') else None,
        'read': msg.get('read', False),
        'direction': direcao,
    }

    if nomes and outro_id in nomes:
        dados['other_user_name'] = nomes[outro_id].get('nome')
        dados['other_user_type'] = normalizar_tipo(nomes[outro_id].get('tipo'))

    return dados


def _carregar_nomes(mensagens, current_user_id):
    """Carrega nome/tipo dos interlocutores em uma consulta so."""
    from app import mongo

    ids = set()
    for msg in mensagens:
        for campo in ('from_user_id', 'to_user_id'):
            if str(msg[campo]) != str(current_user_id):
                ids.add(msg[campo])

    if not ids:
        return {}

    return {
        u['_id']: u
        for u in mongo.db.users.find({'_id': {'$in': list(ids)}}, {'nome': 1, 'tipo': 1})
    }


@message_blueprint.route('/message', methods=['POST'])
@message_blueprint.route('/messages', methods=['POST'])
@token_required
def send_message(current_user):
    """Envia uma mensagem a um usuario de perfil diferente."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('to_user_id') or not data.get('content'):
            return dados_invalidos('Destinatario e conteudo sao obrigatorios')

        conteudo = str(data['content']).strip()
        if not conteudo:
            return dados_invalidos('O conteudo da mensagem nao pode ser vazio')
        if len(conteudo) > CONTEUDO_MAX:
            return dados_invalidos(f'A mensagem excede {CONTEUDO_MAX} caracteres')

        destinatario_oid = to_object_id(data['to_user_id'])
        if destinatario_oid is None:
            return dados_invalidos('to_user_id invalido')

        if str(destinatario_oid) == str(current_user['_id']):
            return dados_invalidos('Nao e possivel enviar mensagem para si mesmo')

        destinatario = user_model.find_user_by_id(destinatario_oid)
        if not destinatario:
            return nao_encontrado('Destinatario nao encontrado')

        tipo_atual = normalizar_tipo(current_user.get('tipo'))
        tipo_destinatario = normalizar_tipo(destinatario.get('tipo'))

        if tipo_atual == tipo_destinatario:
            return nao_autorizado(
                'So e permitido enviar mensagens para perfis diferentes'
            )

        if ADMIN not in (tipo_atual, tipo_destinatario) and not pode_enviar_mensagem(current_user, destinatario):
            return nao_autorizado(
                'Voce so pode enviar mensagens para quem tem vinculo pedagogico ou familiar comprovado'
            )

        resultado = message_model.create_message(
            str(current_user['_id']),
            str(destinatario_oid),
            conteudo,
            data.get('message_type', 'text'),
            data.get('priority', 'normal'),
        )

        # Notifica o destinatario (falha aqui nao invalida o envio)
        try:
            from app.Controllers.notification_controller import NotificationService
            NotificationService.notify_new_message(
                str(destinatario_oid),
                current_user.get('nome', ''),
                conteudo,
                str(resultado.inserted_id),
            )
        except Exception as e:
            logger.warning('Falha ao criar notificacao de mensagem: %s', e)

        return sucesso(
            message='Mensagem enviada com sucesso!',
            status_code=201,
            message_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao enviar mensagem')


@message_blueprint.route('/messages', methods=['GET'])
@token_required
def get_messages(current_user):
    """Lista as mensagens do usuario."""
    try:
        limit = max(1, min(request.args.get('limit', 50, type=int) or 50, 200))
        skip = max(0, request.args.get('skip', 0, type=int) or 0)
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'

        mensagens = [
            m for m in message_model.get_user_messages(
                str(current_user['_id']), limit, skip, unread_only
            )
            if not m.get('deleted')
        ]

        nomes = _carregar_nomes(mensagens, current_user['_id'])
        data = [_serializar(m, current_user['_id'], nomes) for m in mensagens]

        return sucesso(data=data, total=len(data))

    except Exception as e:
        return erro_interno(e, 'ao listar mensagens')


@message_blueprint.route('/messages/conversations', methods=['GET'])
@token_required
def get_conversations(current_user):
    """Lista as conversas do usuario, com a ultima mensagem de cada uma."""
    try:
        mensagens = [
            m for m in message_model.get_user_messages(str(current_user['_id']), limit=1000)
            if not m.get('deleted')
        ]

        nomes = _carregar_nomes(mensagens, current_user['_id'])
        conversas = {}

        for msg in mensagens:
            eh_saida = str(msg['from_user_id']) == str(current_user['_id'])
            outro_id = msg['to_user_id'] if eh_saida else msg['from_user_id']
            chave = str(outro_id)

            # As mensagens vem ordenadas desc: a primeira e a mais recente
            if chave in conversas:
                if not msg.get('read') and not eh_saida:
                    conversas[chave]['unread_count'] += 1
                continue

            outro = nomes.get(outro_id)
            if not outro:
                continue

            conversas[chave] = {
                'user_id': chave,
                'user_name': outro.get('nome'),
                'user_type': normalizar_tipo(outro.get('tipo')),
                'last_message': msg['content'],
                'last_message_time': msg['timestamp'].isoformat() if msg.get('timestamp') else None,
                'last_message_direction': 'outgoing' if eh_saida else 'incoming',
                'unread_count': 1 if (not msg.get('read') and not eh_saida) else 0,
            }

        return sucesso(data=list(conversas.values()))

    except Exception as e:
        return erro_interno(e, 'ao listar conversas')


@message_blueprint.route('/messages/conversation/<other_user_id>', methods=['GET'])
@token_required
def get_conversation(current_user, other_user_id):
    """Historico de mensagens trocadas com outro usuario."""
    try:
        outro_oid = to_object_id(other_user_id)
        if outro_oid is None:
            return dados_invalidos('ID de usuario invalido')

        limit = max(1, min(request.args.get('limit', 50, type=int) or 50, 200))
        mensagens = [
            m for m in message_model.get_conversation(
                str(current_user['_id']), str(outro_oid), limit
            )
            if not m.get('deleted')
        ]

        nomes = _carregar_nomes(mensagens, current_user['_id'])
        return sucesso(data=[_serializar(m, current_user['_id'], nomes) for m in mensagens])

    except Exception as e:
        return erro_interno(e, 'ao buscar conversa')


@message_blueprint.route('/messages/<message_id>/read', methods=['PUT'])
@token_required
def mark_message_read(current_user, message_id):
    """Marca uma mensagem recebida como lida."""
    try:
        resultado = message_model.mark_as_read(message_id, str(current_user['_id']))

        if resultado is None or resultado.matched_count == 0:
            return nao_encontrado('Mensagem nao encontrada')

        return sucesso(message='Mensagem marcada como lida')

    except Exception as e:
        return erro_interno(e, 'ao marcar mensagem como lida')


@message_blueprint.route('/messages/conversation/<other_user_id>/read', methods=['PUT'])
@token_required
def mark_conversation_read(current_user, other_user_id):
    """Marca toda a conversa como lida."""
    try:
        outro_oid = to_object_id(other_user_id)
        if outro_oid is None:
            return dados_invalidos('ID de usuario invalido')

        resultado = message_model.mark_conversation_read(
            str(current_user['_id']), str(outro_oid)
        )

        return sucesso(
            message=f'{resultado.modified_count} mensagens marcadas como lidas'
        )

    except Exception as e:
        return erro_interno(e, 'ao marcar conversa como lida')


@message_blueprint.route('/messages/unread/count', methods=['GET'])
@token_required
def get_unread_count(current_user):
    """Conta as mensagens nao lidas."""
    try:
        return sucesso(count=message_model.get_unread_count(str(current_user['_id'])))
    except Exception as e:
        return erro_interno(e, 'ao contar mensagens nao lidas')


@message_blueprint.route('/messages/<message_id>', methods=['DELETE'])
@token_required
def delete_message(current_user, message_id):
    """Arquiva uma mensagem para o usuario."""
    try:
        resultado = message_model.delete_message(message_id, str(current_user['_id']))

        if resultado is None or resultado.matched_count == 0:
            return nao_encontrado('Mensagem nao encontrada')

        return sucesso(message='Mensagem deletada')

    except Exception as e:
        return erro_interno(e, 'ao deletar mensagem')
