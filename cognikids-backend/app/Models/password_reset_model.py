"""
Recuperacao de senha por token de uso unico.

O token nunca e' devolvido na resposta HTTP em nenhuma circunstancia — so'
o hash (sha256) fica no banco, e o valor bruto so' existe no momento da
criacao, para ser entregue por um canal fora da API (ver
app/Utils/email_service.py). Isso garante que a rota e' segura por padrao
mesmo em ambiente sem servidor de e-mail configurado: sem e-mail, o pior
caso e' o usuario nao receber o token, nunca um terceiro conseguir le-lo
pela API.
"""

import datetime
import hashlib
import logging
import secrets

from bson.objectid import ObjectId

from app import mongo

logger = logging.getLogger(__name__)

TOKEN_VALIDADE_MINUTOS = 60


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


def _hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


class PasswordReset:
    def criar_token(self, user_id):
        """Gera um token novo e invalida qualquer token anterior ainda
        valido deste usuario — pedir recuperacao de novo nao deixa dois
        tokens ativos ao mesmo tempo."""
        user_oid = _to_object_id(user_id)
        if user_oid is None:
            return None

        agora = datetime.datetime.utcnow()

        mongo.db.password_resets.update_many(
            {'user_id': user_oid, 'usado_em': None},
            {'$set': {'usado_em': agora}},
        )

        token = secrets.token_urlsafe(32)
        mongo.db.password_resets.insert_one({
            'user_id': user_oid,
            'token_hash': _hash(token),
            'criado_em': agora,
            'expira_em': agora + datetime.timedelta(minutes=TOKEN_VALIDADE_MINUTOS),
            'usado_em': None,
        })
        return token

    def consumir_token(self, token):
        """Valida e marca o token como usado numa unica operacao atomica
        (find_one_and_update), para que duas requisicoes simultaneas com o
        mesmo token nunca consigam trocar a senha duas vezes.

        Retorna o documento (com user_id) se o token era valido, ou None se
        invalido, expirado ou ja utilizado.
        """
        if not token:
            return None

        agora = datetime.datetime.utcnow()
        return mongo.db.password_resets.find_one_and_update(
            {
                'token_hash': _hash(token),
                'usado_em': None,
                'expira_em': {'$gt': agora},
            },
            {'$set': {'usado_em': agora}},
        )
