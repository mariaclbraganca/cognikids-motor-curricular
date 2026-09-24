"""Verifica se o serviço core (cognikids-backend) está acessível via GET.

Uso: python scripts/health_check.py
Variável de ambiente: CORE_BASE_URL (default http://localhost:5001)
"""

import os
import sys

import httpx

CORE_BASE_URL = os.environ.get("CORE_BASE_URL", "http://localhost:5001")
TIMEOUT_SECONDS = 5


def main() -> int:
    url = f"{CORE_BASE_URL}/api/status"
    try:
        resposta = httpx.get(url, timeout=TIMEOUT_SECONDS)
    except httpx.RequestError as erro:
        print(f"FALHA: não foi possível conectar em {url} ({erro})")
        return 1

    if resposta.status_code != 200:
        print(f"FALHA: {url} respondeu {resposta.status_code}")
        return 1

    corpo = resposta.json()
    print(f"OK: core acessível em {url} — {corpo}")
    return 0 if corpo.get("database") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
