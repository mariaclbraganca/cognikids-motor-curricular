"""
Perfil funcional de acessibilidade.

O responsavel responde sobre necessidades observaveis do filho; o sistema
deriva os tokens de interface. A crianca ajusta conforto dentro de limites.

Nenhum endpoint aqui recebe ou devolve diagnostico.
"""

import logging

from flask import Blueprint, request

from app.Models.accessibility_profile_model import AccessibilityProfile
from app.Utils.accessibility import (
    AJUSTAVEIS_PELA_CRIANCA,
    catalogo_publico,
    validar_respostas,
)
from app.Utils.authz import filhos_do_responsavel, pode_ver_aluno, to_object_id
from app.Utils.decorators import estudante_required, responsavel_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    sucesso,
)

logger = logging.getLogger(__name__)

accessibility_blueprint = Blueprint('accessibility', __name__)
profile_model = AccessibilityProfile()


@accessibility_blueprint.route('/questionnaire', methods=['GET'])
@token_required
def get_questionnaire(current_user):
    """Perguntas sobre necessidades observaveis, para o responsavel."""
    return sucesso(data={
        'perguntas': catalogo_publico(),
        'ajustaveis_pela_crianca': list(AJUSTAVEIS_PELA_CRIANCA),
    })


@accessibility_blueprint.route('/me', methods=['GET'])
@token_required
def get_my_profile(current_user):
    """Tokens de interface do proprio usuario.

    Chamado pelo app do aluno no login para configurar a interface.
    """
    try:
        return sucesso(data=profile_model.serializar(current_user['_id']))
    except Exception as e:
        return erro_interno(e, 'ao carregar perfil de acessibilidade')


@accessibility_blueprint.route('/me/comfort', methods=['PUT'])
@token_required
@estudante_required
def set_my_comfort(current_user):
    """Painel de conforto: a crianca ajusta o que lhe cabe ajustar.

    Apenas estimulo, densidade e texto. Os demais tokens sao protecoes
    definidas pelo responsavel e nao podem ser desfeitas por um toque.
    """
    try:
        data = request.get_json(silent=True) or {}
        ajustes = data.get('ajustes', data)

        if not isinstance(ajustes, dict) or not ajustes:
            return dados_invalidos('Informe os ajustes desejados')

        ignorados = [k for k in ajustes if k not in AJUSTAVEIS_PELA_CRIANCA]

        profile_model.salvar_ajustes_crianca(current_user['_id'], ajustes)

        return sucesso(
            message='Pronto, sua tela foi ajustada.',
            data=profile_model.serializar(current_user['_id']),
            ignorados=ignorados,
        )

    except Exception as e:
        return erro_interno(e, 'ao salvar ajustes de conforto')


@accessibility_blueprint.route('/<string:aluno_id>', methods=['GET'])
@token_required
def get_profile(current_user, aluno_id):
    """Perfil de um aluno (responsavel vinculado ou professor da turma)."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado aos dados deste aluno')

        return sucesso(data=profile_model.serializar(aluno_oid))

    except Exception as e:
        return erro_interno(e, 'ao consultar perfil de acessibilidade')


@accessibility_blueprint.route('/<string:aluno_id>/history', methods=['GET'])
@token_required
def get_history(current_user, aluno_id):
    """Rastro de auditoria: quem mudou o que e quando no perfil de acessibilidade."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado aos dados deste aluno')

        eventos = profile_model.historico(aluno_oid)
        return sucesso(data=[AccessibilityProfile.serializar_evento(e) for e in eventos])

    except Exception as e:
        return erro_interno(e, 'ao consultar historico do perfil de acessibilidade')


@accessibility_blueprint.route('/<string:aluno_id>', methods=['PUT'])
@token_required
@responsavel_required
def set_profile(current_user, aluno_id):
    """Responsavel informa as necessidades observaveis do filho."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if aluno_oid not in filhos_do_responsavel(current_user):
            return nao_autorizado('Este aluno nao esta vinculado a voce')

        data = request.get_json(silent=True) or {}
        respostas_brutas = data.get('respostas', data)

        respostas, erros = validar_respostas(respostas_brutas)
        if erros:
            return dados_invalidos('Respostas invalidas', erros=erros)

        if not respostas:
            return dados_invalidos('Nenhuma resposta valida foi enviada')

        profile_model.salvar_respostas(aluno_oid, respostas, current_user['_id'])

        return sucesso(
            message='Perfil atualizado. A tela do seu filho ja foi ajustada.',
            data=profile_model.serializar(aluno_oid),
        )

    except Exception as e:
        return erro_interno(e, 'ao salvar perfil de acessibilidade')
