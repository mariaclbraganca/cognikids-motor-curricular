"""
Agenda escolar: aulas, provas, eventos e reunioes.

Professor cria eventos nas proprias turmas; aluno ve os eventos das suas
turmas; responsavel ve os eventos das turmas dos filhos.

Os filtros usam ObjectId porque e assim que Schedule.create_event grava o
class_id. A versao anterior montava os filtros com strings, e nenhum evento
casava.
"""

import logging

from flask import Blueprint, request

from app.Models.class_model import Class
from app.Models.schedule_model import Schedule
from app.Models.user_model import User
from app.Utils.authz import (
    filhos_do_responsavel,
    ids_iguais,
    pode_editar_turma,
    pode_ver_turma,
    to_object_id,
    turmas_do_professor,
)
from app.Utils.decorators import roles_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)
from app.Utils.roles import ADMIN, ESTUDANTE, PROFESSOR, RESPONSAVEL, normalizar_tipo

logger = logging.getLogger(__name__)

schedule_blueprint = Blueprint('schedule', __name__)
schedule_model = Schedule()
class_model = Class()
user_model = User()


def _turmas_visiveis(current_user):
    """ObjectIds das turmas visiveis ao usuario, conforme o perfil."""
    tipo = normalizar_tipo(current_user.get('tipo'))

    if tipo in (PROFESSOR, ADMIN):
        return turmas_do_professor(current_user)

    if tipo == ESTUDANTE:
        return {
            t['_id'] for t in class_model.get_student_classes(str(current_user['_id']))
        }

    if tipo == RESPONSAVEL:
        return {
            t['_id']
            for t in class_model.get_parent_classes(filhos_do_responsavel(current_user))
        }

    return set()


def _serializar(evento):
    created_at = evento.get('created_at')
    return {
        '_id': str(evento['_id']),
        'title': evento.get('title'),
        'type': evento.get('type'),
        'subject': evento.get('subject', ''),
        'description': evento.get('description', ''),
        'class_id': str(evento['class_id']) if evento.get('class_id') else None,
        'start_date': evento.get('start_date'),
        'end_date': evento.get('end_date'),
        'all_day': evento.get('all_day', False),
        'location': evento.get('location', ''),
        'color': evento.get('color', '#3B82F6'),
        'reminder': evento.get('reminder'),
        'created_by': str(evento['created_by']) if evento.get('created_by') else None,
        'participants': [str(p) for p in evento.get('participants', [])],
        'created_at': created_at.isoformat() if created_at else None,
    }


def _pode_ver_evento(current_user, evento):
    """Criador, participante ou membro da turma do evento."""
    if ids_iguais(evento.get('created_by'), current_user.get('_id')):
        return True

    proprio = to_object_id(current_user.get('_id'))
    if proprio in (evento.get('participants') or []):
        return True

    if evento.get('class_id'):
        return evento['class_id'] in _turmas_visiveis(current_user)

    return False


@schedule_blueprint.route('/events', methods=['POST'])
@token_required
@roles_required(PROFESSOR, ADMIN)
def create_event(current_user):
    """(PROFESSOR) Cria um evento na agenda."""
    try:
        data = request.get_json(silent=True) or {}
        obrigatorios = ['title', 'type', 'start_date', 'end_date']
        faltando = [c for c in obrigatorios if not data.get(c)]
        if faltando:
            return dados_invalidos(f'Campos obrigatorios em falta: {", ".join(faltando)}')

        if data.get('class_id'):
            turma = class_model.get_class_by_id(data['class_id'])
            if not turma:
                return nao_encontrado('Turma nao encontrada')
            if not pode_editar_turma(current_user, turma):
                return nao_autorizado('Acesso nao autorizado a esta turma')

        resultado = schedule_model.create_event({
            'title': data['title'],
            'type': data['type'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'class_id': data.get('class_id'),
            'subject': data.get('subject', ''),
            'description': data.get('description', ''),
            'all_day': data.get('all_day', False),
            'location': data.get('location', ''),
            'created_by': current_user['_id'],
            'participants': data.get('participants', []),
            'reminder': data.get('reminder'),
            'color': data.get('color', '#3B82F6'),
        })

        return sucesso(
            message='Evento criado com sucesso!',
            status_code=201,
            event_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao criar evento')


@schedule_blueprint.route('/events', methods=['GET'])
@token_required
def get_events(current_user):
    """Lista os eventos visiveis ao usuario."""
    try:
        turmas_ids = _turmas_visiveis(current_user)
        user_oid = to_object_id(current_user['_id'])

        class_id = request.args.get('class_id')
        if class_id:
            turma_oid = to_object_id(class_id)
            if turma_oid is None:
                return dados_invalidos('class_id invalido')
            if turma_oid not in turmas_ids:
                return nao_autorizado('Acesso nao autorizado a esta turma')
            query_filter = {'class_id': turma_oid}
        else:
            query_filter = {
                '$or': [
                    {'created_by': user_oid},
                    {'participants': user_oid},
                    {'class_id': {'$in': list(turmas_ids)}},
                ]
            }

        eventos = schedule_model.get_events_by_filter(
            query_filter,
            request.args.get('start_date'),
            request.args.get('end_date'),
        )

        return sucesso(data=[_serializar(e) for e in eventos])

    except Exception as e:
        return erro_interno(e, 'ao listar eventos')


@schedule_blueprint.route('/events/<event_id>', methods=['GET'])
@token_required
def get_event(current_user, event_id):
    """Detalhes de um evento."""
    try:
        evento = schedule_model.get_event_by_id(event_id)
        if not evento:
            return nao_encontrado('Evento nao encontrado')

        if not _pode_ver_evento(current_user, evento):
            return nao_autorizado('Acesso nao autorizado a este evento')

        return sucesso(data=_serializar(evento))

    except Exception as e:
        return erro_interno(e, 'ao buscar evento')


@schedule_blueprint.route('/events/<event_id>', methods=['PUT'])
@token_required
def update_event(current_user, event_id):
    """Atualiza um evento (apenas o criador)."""
    try:
        evento = schedule_model.get_event_by_id(event_id)
        if not evento:
            return nao_encontrado('Evento nao encontrado')

        if not ids_iguais(evento.get('created_by'), current_user.get('_id')):
            return nao_autorizado('Apenas o criador pode editar o evento')

        data = request.get_json(silent=True) or {}
        permitidos = {
            'title', 'description', 'start_date', 'end_date', 'location',
            'color', 'all_day', 'reminder', 'subject', 'type',
        }
        atualizacao = {k: v for k, v in data.items() if k in permitidos}

        if not atualizacao:
            return dados_invalidos('Nenhum campo valido para atualizar')

        schedule_model.update_event(event_id, atualizacao)
        return sucesso(message='Evento atualizado com sucesso!')

    except Exception as e:
        return erro_interno(e, 'ao atualizar evento')


@schedule_blueprint.route('/events/<event_id>', methods=['DELETE'])
@token_required
def delete_event(current_user, event_id):
    """Exclui um evento (apenas o criador)."""
    try:
        evento = schedule_model.get_event_by_id(event_id)
        if not evento:
            return nao_encontrado('Evento nao encontrado')

        if not ids_iguais(evento.get('created_by'), current_user.get('_id')):
            return nao_autorizado('Apenas o criador pode excluir o evento')

        schedule_model.delete_event(event_id)
        return sucesso(message='Evento excluido com sucesso!')

    except Exception as e:
        return erro_interno(e, 'ao excluir evento')


@schedule_blueprint.route('/events/upcoming', methods=['GET'])
@token_required
def get_upcoming_events(current_user):
    """Proximos eventos do usuario."""
    try:
        import datetime

        dias = max(1, min(request.args.get('dias', 7, type=int) or 7, 90))
        agora = datetime.datetime.utcnow()

        turmas_ids = _turmas_visiveis(current_user)
        user_oid = to_object_id(current_user['_id'])

        eventos = schedule_model.get_events_by_filter(
            {'$or': [
                {'created_by': user_oid},
                {'participants': user_oid},
                {'class_id': {'$in': list(turmas_ids)}},
            ]},
            agora.isoformat(),
            (agora + datetime.timedelta(days=dias)).isoformat(),
        )

        return sucesso(data=[_serializar(e) for e in eventos])

    except Exception as e:
        return erro_interno(e, 'ao listar proximos eventos')
