import logging
from functools import wraps

import jwt
from flask import request, current_app

from app.Utils.responses import erro, nao_autorizado
from app.Utils.roles import (
    normalizar_tipo,
    PROFESSOR,
    ESTUDANTE,
    RESPONSAVEL,
    ADMIN,
)

logger = logging.getLogger(__name__)


def _extrair_token():
    """Le o token do header Authorization no formato 'Bearer <token>'."""
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return None

    partes = auth_header.split()
    if len(partes) == 2 and partes[0].lower() == 'bearer':
        return partes[1]

    # Token enviado sem o prefixo Bearer (clientes antigos do dashboard)
    if len(partes) == 1:
        return partes[0]

    return None


def token_required(f):
    """Exige um JWT valido e injeta o usuario autenticado como 1o argumento."""

    @wraps(f)
    def decorated(*args, **kwargs):
        # Import local: evita ciclo de importacao com app.Models
        from app.Models.user_model import User

        token = _extrair_token()
        if not token:
            return erro('Token em falta!', 401)

        try:
            data = jwt.decode(
                token,
                current_app.config['SECRET_KEY'],
                algorithms=['HS256'],
                options={'require': ['exp', 'user_id']},
            )
        except jwt.ExpiredSignatureError:
            return erro('Token expirado!', 401)
        except jwt.InvalidTokenError as e:
            # Nunca logar o token nem a chave de assinatura
            logger.warning('Token invalido recebido: %s', type(e).__name__)
            return erro('Token invalido!', 401)

        current_user = User().find_user_by_id(data.get('user_id'))
        if current_user is None:
            return erro('Token invalido! (Utilizador nao encontrado)', 401)

        return f(current_user, *args, **kwargs)

    return decorated


def roles_required(*tipos_canonicos):
    """Restringe a rota aos perfis informados.

    Deve ser aplicado abaixo de @token_required, que injeta current_user:

        @route(...)
        @token_required
        @roles_required(PROFESSOR)
        def handler(current_user): ...
    """

    def decorator(f):
        @wraps(f)
        def decorated(current_user, *args, **kwargs):
            if normalizar_tipo(current_user.get('tipo')) not in tipos_canonicos:
                return nao_autorizado(
                    'Acesso nao autorizado para o seu perfil de usuario'
                )
            return f(current_user, *args, **kwargs)

        return decorated

    return decorator


def professor_required(f):
    return roles_required(PROFESSOR, ADMIN)(f)


def estudante_required(f):
    return roles_required(ESTUDANTE)(f)


def responsavel_required(f):
    return roles_required(RESPONSAVEL)(f)
