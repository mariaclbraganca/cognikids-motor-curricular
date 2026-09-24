"""
Envio de e-mail transacional (recuperacao de senha).

O projeto nao tem hoje nenhuma forma real de entregar e-mail: nenhuma lib de
envio no requirements.txt, nenhum provedor contratado, nenhuma URL de
frontend publicada para compor um link de redefinicao. Inventar qualquer
uma dessas coisas aqui violaria a regra do CLAUDE.md secao 1 (nunca
inventar dado/URL nao verificado).

Por isso o envio fica atras de EMAIL_SMTP_HOST: se configurado, tenta
enviar via SMTP puro (smtplib da biblioteca padrao, sem dependencia nova);
se nao, cai no fallback de log — o token so aparece no log do servidor,
nunca na resposta HTTP. A rota de recuperacao (auth_controller.py) fica
segura por padrao mesmo sem e-mail configurado, no mesmo espirito do
MODELO_VALIDADO em alert_model.py: a ausencia de configuracao vira um
sinal visivel em log, nunca um vazamento silencioso nem uma falha dura.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def enviar_email_recuperacao(destinatario, token, validade_minutos):
    smtp_host = os.environ.get('EMAIL_SMTP_HOST')

    if not smtp_host:
        logger.warning(
            'EMAIL_SMTP_HOST nao configurado — token de recuperacao para %s '
            'nao foi enviado por e-mail, apenas registrado aqui (uso em '
            'desenvolvimento): %s',
            destinatario, token,
        )
        return False

    smtp_port = int(os.environ.get('EMAIL_SMTP_PORT', '587'))
    smtp_user = os.environ.get('EMAIL_SMTP_USER')
    smtp_password = os.environ.get('EMAIL_SMTP_PASSWORD')
    remetente = os.environ.get('EMAIL_REMETENTE', smtp_user or 'no-reply@cognikids.local')

    mensagem = EmailMessage()
    mensagem['Subject'] = 'CogniKids - Recuperacao de senha'
    mensagem['From'] = remetente
    mensagem['To'] = destinatario
    mensagem.set_content(
        'Voce pediu para redefinir sua senha no CogniKids.\n\n'
        f'Codigo de recuperacao: {token}\n\n'
        f'Ele expira em {validade_minutos} minutos. Se voce nao pediu isso, '
        'ignore este e-mail.'
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as servidor:
            servidor.starttls()
            if smtp_user and smtp_password:
                servidor.login(smtp_user, smtp_password)
            servidor.send_message(mensagem)
        logger.info('E-mail de recuperacao enviado para %s', destinatario)
        return True
    except Exception as e:
        logger.error('Falha ao enviar e-mail de recuperacao para %s: %s', destinatario, e)
        return False
