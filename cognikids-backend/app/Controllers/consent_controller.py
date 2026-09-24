"""
Consentimento do responsavel (LGPD).

O responsavel legal e o unico que concede ou revoga. Professor e aluno
podem consultar o estado, porque ele determina o que cada um pode ver e
fazer — mas nao podem altera-lo.
"""

import logging

from flask import Blueprint, request

from app.Models.consent_model import Consent, FINALIDADES
from app.Utils.authz import filhos_do_responsavel, pode_ver_aluno, to_object_id
from app.Utils.decorators import responsavel_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    sucesso,
)

logger = logging.getLogger(__name__)

consent_blueprint = Blueprint('consent', __name__)
consent_model = Consent()


@consent_blueprint.route('/terms', methods=['GET'])
@token_required
def get_terms(current_user):
    """Texto das finalidades de consentimento, para exibir ao responsavel."""
    return sucesso(data=Consent.termo_publico())


@consent_blueprint.route('/<string:aluno_id>', methods=['GET'])
@token_required
def get_consent(current_user, aluno_id):
    """Estado atual do consentimento de um aluno."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado aos dados deste aluno')

        estado = consent_model.estado(aluno_oid)
        return sucesso(data={
            'aluno_id': str(aluno_oid),
            'finalidades': estado,
            'completo': all(
                estado.get(f) for f, m in FINALIDADES.items() if m['obrigatorio']
            ),
        })

    except Exception as e:
        return erro_interno(e, 'ao consultar consentimento')


@consent_blueprint.route('/<string:aluno_id>', methods=['PUT'])
@token_required
@responsavel_required
def set_consent(current_user, aluno_id):
    """Concede ou revoga finalidades. Apenas o responsavel vinculado."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if aluno_oid not in filhos_do_responsavel(current_user):
            return nao_autorizado('Este aluno nao esta vinculado a voce')

        data = request.get_json(silent=True) or {}
        finalidades = data.get('finalidades')

        if not isinstance(finalidades, dict) or not finalidades:
            return dados_invalidos(
                'Informe o objeto "finalidades" com os valores desejados'
            )

        desconhecidas = [f for f in finalidades if f not in FINALIDADES]
        if desconhecidas:
            return dados_invalidos(
                f'Finalidades desconhecidas: {", ".join(desconhecidas)}'
            )

        estado, avisos = consent_model.registrar(
            aluno_oid, finalidades, current_user['_id'], request.remote_addr
        )

        return sucesso(
            message='Consentimento atualizado',
            data={'aluno_id': str(aluno_oid), 'finalidades': estado},
            avisos=avisos,
        )

    except Exception as e:
        return erro_interno(e, 'ao registrar consentimento')


@consent_blueprint.route('/<string:aluno_id>', methods=['DELETE'])
@token_required
@responsavel_required
def revoke_all(current_user, aluno_id):
    """Revoga todas as finalidades de uma vez.

    Revogar precisa ser tao simples quanto consentir (LGPD art. 8o, §5o).
    """
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if aluno_oid not in filhos_do_responsavel(current_user):
            return nao_autorizado('Este aluno nao esta vinculado a voce')

        estado, _ = consent_model.revogar_tudo(
            aluno_oid, current_user['_id'], request.remote_addr
        )

        return sucesso(
            message=(
                'Consentimento revogado. A coleta de dados foi interrompida, o '
                'professor deixa de ver os dados do aluno, e o historico '
                'biometrico da pulseira (batimentos, movimento) foi eliminado.'
            ),
            data={'aluno_id': str(aluno_oid), 'finalidades': estado},
        )

    except Exception as e:
        return erro_interno(e, 'ao revogar consentimento')


@consent_blueprint.route('/<string:aluno_id>/history', methods=['GET'])
@token_required
@responsavel_required
def get_history(current_user, aluno_id):
    """Rastro de auditoria: quem mudou o que e quando."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if aluno_oid not in filhos_do_responsavel(current_user):
            return nao_autorizado('Este aluno nao esta vinculado a voce')

        eventos = consent_model.historico(aluno_oid)
        return sucesso(data=[Consent.serializar_evento(e) for e in eventos])

    except Exception as e:
        return erro_interno(e, 'ao consultar historico de consentimento')
