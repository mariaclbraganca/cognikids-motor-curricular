"""Cliente HTTP read-only para o core — checagem de consentimento.

So GET, nunca escreve no core (ver CLAUDE.md secao 4 — regras da fronteira).
Autentica com um JWT de servico assinado com o mesmo CORE_JWT_SECRET do
Flask core, mesmo padrao ja usado em workers/core_client.py.

Usado para bloquear a ingestao de telemetria de um aluno sem consentimento
de uso do app — antes desta correcao, o gateway aceitava e persistia
qualquer evento de qualquer aluno autenticado, sem checar consentimento
nenhum.
"""

import datetime

import httpx
import jwt

from app.core.config import settings

TIMEOUT_SECONDS = 5


def _emitir_token_servico() -> str:
    agora = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": settings.core_service_user_id,
        "exp": agora + datetime.timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.core_jwt_secret, algorithm="HS256")


async def consentimento_permite_uso_app(aluno_id: str) -> bool | None:
    """GET /api/consent/{aluno_id} — a finalidade uso_app esta concedida?

    Retorna None se o core estiver inacessivel ou a resposta for
    inesperada — o chamador deve tratar None como "nao aceitar", nunca como
    "aceitar por padrao": e ingestao de dado novo de uma crianca, o lado
    seguro do erro e recusar, nao gravar sem confirmar consentimento.
    """
    token = _emitir_token_servico()
    url = f"{settings.core_base_url}/api/consent/{aluno_id}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as cliente:
            resposta = await cliente.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.RequestError:
        return None

    if resposta.status_code != 200:
        return None

    corpo = resposta.json()
    finalidades = corpo.get("data", {}).get("finalidades", {})
    return bool(finalidades.get("uso_app"))


async def alunos_visiveis_do_professor(teacher_id: str, autorizacao: str) -> set[str] | None:
    """IDs dos alunos que este professor pode ver, segundo o proprio core.

    Chama com o token do PROPRIO professor, nao com o JWT de servico: o
    gateway deve agir com a autoridade de quem pediu, nunca com autoridade
    elevada. O core aplica `alunos_visiveis` nessa rota, que ja filtra por
    consentimento de compartilhamento com a escola — entao um aluno cujo
    responsavel revogou o compartilhamento simplesmente nao volta aqui.

    Retorna None se o core estiver inacessivel: o chamador deve recusar,
    nunca liberar por padrao.
    """
    url = f"{settings.core_base_url}/api/teachers/{teacher_id}/students"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as cliente:
            resposta = await cliente.get(url, headers={"Authorization": autorizacao})
    except httpx.RequestError:
        return None

    if resposta.status_code != 200:
        return None

    corpo = resposta.json()
    return {str(aluno.get("_id")) for aluno in corpo.get("data", []) if aluno.get("_id")}
