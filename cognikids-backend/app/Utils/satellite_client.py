"""
Chamada core -> satelite, para a cascata de revogacao de consentimento.

Ate esta correcao, so existia comunicacao satelite -> core (core_client.py
no satelite, GET read-only). Revogar coleta_biometrica no core ja apaga
registros_iot e alerts (ADR-008), mas o satelite deriva do mesmo dado
comportamental o proprio grafo de conhecimento (student_graphs) e a
telemetria bruta (telemetry_events) — e nada avisava o satelite disso
(ADR-008 registrou a lacuna; ADR-010 a lista como aberta).

Regra de fronteira que esta chamada tem que respeitar (CLAUDE.md secao 2 /
ADR-001, regra 3): o core continua funcionando mesmo que o satelite esteja
fora do ar. Por isso esta chamada e' SEMPRE best-effort — nunca levanta
excecao, nunca bloqueia nem reverte a revogacao no core se o satelite nao
responder. Falha aqui vira aviso em log, nunca erro para quem revogou.
"""

import datetime
import logging

import jwt
import requests
from flask import current_app

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5


def _emitir_token_servico():
    """JWT de servico, no mesmo formato/segredo que o core ja valida.

    Nao carrega user_id nem role de usuario humano de proposito: o claim
    'servico' marca que quem chama e' o proprio core, nao alguem agindo em
    nome de um usuario — a rota do satelite que recebe isto (ver
    servico_core_autenticado no gateway) rejeita qualquer token sem esse
    claim, mesmo que seja um JWT de usuario valido. Vida curta (5 min,
    mesmo padrao do token de servico satelite->core em core_client.py):
    e' emitido e usado na hora, nao precisa durar.
    """
    expira_em = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)
    return jwt.encode(
        {'servico': 'core', 'exp': expira_em},
        current_app.config['SECRET_KEY'],
        algorithm='HS256',
    )


def notificar_revogacao_biometrica(aluno_id):
    """Pede ao satelite para apagar o grafo de conhecimento e a telemetria
    do aluno. Best-effort: qualquer falha fica em log, nunca em excecao.
    """
    base_url = current_app.config.get('SATELLITE_BASE_URL', 'http://localhost:8001')
    url = f'{base_url}/v1/students/{aluno_id}/behavioral-data'

    try:
        token = _emitir_token_servico()
        resposta = requests.delete(
            url,
            headers={'Authorization': f'Bearer {token}'},
            timeout=TIMEOUT_SECONDS,
        )
        if resposta.status_code == 200:
            logger.info(
                'Satelite confirmou a cascata de revogacao para aluno %s: %s',
                aluno_id, resposta.text[:200],
            )
        else:
            logger.warning(
                'Satelite recusou a cascata de revogacao para aluno %s: HTTP %s',
                aluno_id, resposta.status_code,
            )
    except Exception as e:
        # Satelite fora do ar, DNS, timeout — qualquer motivo. O core nao
        # depende do satelite para funcionar (CLAUDE.md secao 2); a limpeza
        # do satelite fica pendente e sera reprocessada manualmente ate
        # existir uma fila de retentativa dedicada.
        logger.warning(
            'Nao foi possivel notificar o satelite da revogacao para aluno %s: %s',
            aluno_id, e,
        )
