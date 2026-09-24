"""Autenticação do gateway via o mesmo JWT que o core (Flask) já emite.

O satélite nunca autentica usuário por conta própria — reaproveita o JWT
assinado com CORE_JWT_SECRET que o core já emite em POST /api/login (ver
cognikids-backend/app/Controllers/auth_controller.py). Sem isso, o gateway
ficava sem autenticação nenhuma: qualquer cliente com acesso de rede podia
criar job de adaptação em nome de qualquer professor ou ler o conteúdo de
qualquer job já existente.
"""

import jwt
from fastapi import Header, HTTPException, status

from app.core.config import settings


def _extrair_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de autenticação ausente")

    partes = authorization.split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    if len(partes) == 1:
        return partes[0]

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cabeçalho Authorization mal formatado")


def usuario_autenticado(authorization: str | None = Header(default=None)) -> dict:
    """Valida o JWT emitido pelo core — aceita qualquer perfil autenticado
    (professor, responsável, aluno, admin). Usado onde a rota só precisa
    saber que existe um usuário real do core por trás da chamada.
    """
    token = _extrair_token(authorization)
    try:
        return jwt.decode(token, settings.core_jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")


def professor_autenticado(authorization: str | None = Header(default=None)) -> dict:
    """Como usuario_autenticado, mas exige role='professor' — só professor
    pode criar job de adaptação curricular em nome de si mesmo.
    """
    usuario = usuario_autenticado(authorization)
    if usuario.get("role") != "professor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Apenas professores podem criar atividades adaptadas",
        )
    return usuario


def servico_core_autenticado(authorization: str | None = Header(default=None)) -> dict:
    """Valida que a chamada vem do próprio core, não de um usuário humano.

    Usado em rotas de efeito administrativo entre serviços (hoje só a
    cascata de revogação de consentimento, ADR-008/ADR-010) — não reaproveita
    usuario_autenticado de propósito: um JWT de usuário válido (professor,
    aluno, responsável) NÃO deve conseguir chamar estas rotas. O core emite
    este token especificamente com o claim 'servico' (ver
    Utils/satellite_client.py no core), nunca com user_id/role de humano.
    """
    token = _extrair_token(authorization)
    try:
        payload = jwt.decode(token, settings.core_jwt_secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    if payload.get("servico") != "core":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta rota só aceita chamadas de serviço do core",
        )
    return payload
