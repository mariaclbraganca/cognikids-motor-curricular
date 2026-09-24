"""
Respostas HTTP padronizadas do CogniKids.

Todas as rotas retornam o mesmo envelope ({'status': ..., 'message': ...}),
e detalhes de excecao nunca chegam ao cliente: sao registrados no log do
servidor e substituidos por uma mensagem generica.
"""

import logging
import traceback

from flask import jsonify

logger = logging.getLogger(__name__)


def sucesso(data=None, message=None, status_code=200, **extras):
    payload = {'status': 'sucesso'}
    if message:
        payload['message'] = message
    if data is not None:
        payload['data'] = data
    payload.update(extras)
    return jsonify(payload), status_code


def erro(message, status_code=400, **extras):
    payload = {'status': 'erro', 'message': message}
    payload.update(extras)
    return jsonify(payload), status_code


def nao_autorizado(message='Acesso nao autorizado'):
    return erro(message, 403)


def nao_encontrado(message='Recurso nao encontrado'):
    return erro(message, 404)


def dados_invalidos(message='Dados invalidos', **extras):
    return erro(message, 400, **extras)


def erro_interno(exc=None, contexto=''):
    """Loga o traceback no servidor e devolve mensagem generica ao cliente.

    Nunca expor str(exc) na resposta: os stack traces vazavam nomes de
    colecoes e estrutura interna do banco.
    """
    if exc is not None:
        logger.error('Erro interno %s: %s', contexto, exc)
        logger.debug(traceback.format_exc())
    return erro('Erro interno do servidor', 500)
