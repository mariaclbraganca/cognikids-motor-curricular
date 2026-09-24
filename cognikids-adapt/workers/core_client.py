"""Cliente HTTP read-only para o core (cognikids-backend).

Só GET, nunca escreve no core (ver CLAUDE.md seção 4 — regras da fronteira).
Autentica com um JWT de serviço assinado com o mesmo CORE_JWT_SECRET do
Flask core, referenciando um usuário admin real que precisa existir na
base do core (o endpoint de perfil de acessibilidade carrega o usuário do
banco por `user_id` do token — não basta o token ser válido, o usuário
também precisa existir e ter `tipo='admin'` para `pode_ver_aluno` liberar
o acesso a qualquer aluno). Ver CORE_SERVICE_USER_ID no .env.example.
"""

import datetime
import os

import httpx
import jwt

CORE_BASE_URL = os.environ.get("CORE_BASE_URL", "http://localhost:5001")
CORE_JWT_SECRET = os.environ.get("CORE_JWT_SECRET", "")
CORE_SERVICE_USER_ID = os.environ.get("CORE_SERVICE_USER_ID", "")

TIMEOUT_SECONDS = 5


def _emitir_token_servico() -> str:
    agora = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": CORE_SERVICE_USER_ID,
        "exp": agora + datetime.timedelta(minutes=5),
    }
    return jwt.encode(payload, CORE_JWT_SECRET, algorithm="HS256")


async def buscar_tokens_acessibilidade(aluno_id: str) -> dict | None:
    """GET /api/accessibility/{aluno_id} — tokens de interface do aluno.

    Retorna None em caso de falha (aluno não encontrado, core fora do ar,
    etc.) — o chamador decide como degradar (ex: seguir com perfil vazio,
    aplicando os padrões conservadores do próprio motor de adaptação).
    """
    token = _emitir_token_servico()
    url = f"{CORE_BASE_URL}/api/accessibility/{aluno_id}"

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as cliente:
            resposta = await cliente.get(url, headers={"Authorization": f"Bearer {token}"})
    except httpx.RequestError:
        return None

    if resposta.status_code != 200:
        return None

    corpo = resposta.json()
    return corpo.get("data", {}).get("tokens")
