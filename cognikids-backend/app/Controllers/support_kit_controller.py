"""
Kit de Apoio do aluno.

Reune informacoes que orientam a resposta a uma crise: interesses,
sensibilidades, estrategias de acalmamento e contatos de emergencia. E
mantido pelo responsavel e consultado pelo professor da turma.

Deliberadamente NAO ha campo de diagnostico — ver o comentario em
app/Models/support_kit_model.py e a ADR-003. O que orienta a conduta e o
comportamento observavel, nao o rotulo.

Estes sao os dados mais sensiveis do sistema, entao a leitura exige vinculo
comprovado: a versao anterior liberava para qualquer professor autenticado.
"""

import datetime
import logging

from flask import Blueprint, request

from app import mongo
from app.Utils.authz import filhos_do_responsavel, pode_ver_aluno, to_object_id
from app.Utils.decorators import responsavel_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

support_kit_bp = Blueprint('support_kit_bp', __name__)


def _serializar(kit):
    last_updated = kit.get('last_updated')
    return {
        '_id': str(kit.get('_id')),
        'aluno_id': str(kit.get('aluno_id')),
        'interesses': kit.get('interesses', []),
        'sensibilidades': kit.get('sensibilidades', []),
        'estrategias_calmantes': kit.get('estrategias_calmantes', ''),
        'contatos_emergencia': kit.get('contatos_emergencia', []),
        'observacoes': kit.get('observacoes', ''),
        'last_updated': last_updated.isoformat() if last_updated else None,
        'updated_by': str(kit['updated_by']) if kit.get('updated_by') else None,
    }


@support_kit_bp.route('/<string:aluno_id>', methods=['POST', 'PUT'])
@token_required
@responsavel_required
def upsert_support_kit(current_user, aluno_id):
    """Cria ou atualiza o Kit de Apoio. Apenas o responsavel vinculado."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if aluno_oid not in filhos_do_responsavel(current_user):
            return nao_autorizado('Este aluno nao esta vinculado a voce')

        data = request.get_json(silent=True) or {}

        # 'neurodivergencia' nao entra, mesmo que o cliente envie: campo
        # removido por violar a ADR-003 (ver support_kit_model.py).
        kit_data = {
            'aluno_id': aluno_oid,
            'interesses': data.get('interesses', []),
            'sensibilidades': data.get('sensibilidades', []),
            'estrategias_calmantes': data.get('estrategias_calmantes', ''),
            'contatos_emergencia': data.get('contatos_emergencia', []),
            'observacoes': data.get('observacoes', ''),
            'last_updated': datetime.datetime.utcnow(),
            'updated_by': current_user['_id'],
        }

        mongo.db.support_kits.update_one(
            {'aluno_id': aluno_oid}, {'$set': kit_data}, upsert=True
        )

        return sucesso(message='Kit de Apoio atualizado com sucesso!')

    except Exception as e:
        return erro_interno(e, 'ao atualizar kit de apoio')


@support_kit_bp.route('/<string:aluno_id>', methods=['GET'])
@token_required
def get_support_kit(current_user, aluno_id):
    """Consulta o Kit de Apoio.

    Acessivel ao responsavel vinculado e ao professor da turma do aluno.
    """
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado ao kit deste aluno')

        kit = mongo.db.support_kits.find_one({'aluno_id': aluno_oid})
        if not kit:
            return nao_encontrado('Kit de Apoio nao encontrado para este aluno.')

        return sucesso(data=_serializar(kit))

    except Exception as e:
        return erro_interno(e, 'ao buscar kit de apoio')


@support_kit_bp.route('/<string:aluno_id>', methods=['DELETE'])
@token_required
@responsavel_required
def delete_support_kit(current_user, aluno_id):
    """Remove o Kit de Apoio. Apenas o responsavel vinculado."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if aluno_oid not in filhos_do_responsavel(current_user):
            return nao_autorizado('Este aluno nao esta vinculado a voce')

        resultado = mongo.db.support_kits.delete_one({'aluno_id': aluno_oid})
        if resultado.deleted_count == 0:
            return nao_encontrado('Kit de Apoio nao encontrado')

        return sucesso(message='Kit de Apoio removido com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover kit de apoio')
