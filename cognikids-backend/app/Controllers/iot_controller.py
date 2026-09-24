# app/Controllers/iot_controller.py
"""
Camada de Percepcao/Aplicacao: ingestao de dados dos dispositivos IoT e
consulta de leituras e alertas.

A ingestao (POST /data) e autenticada por X-API-Key, porque quem chama e a
pulseira, nao um usuario. As consultas usam JWT e respeitam o vinculo do
usuario com o aluno.
"""

import datetime
import hmac
import logging
import os

from bson.objectid import ObjectId
from flask import Blueprint, request

from app import mongo
from app.Models.alert_model import Alert, RegistroIoT, normalizar_biometria
from app.Models.consent_model import COLETA_BIOMETRICA
from app.Utils.authz import (
    alunos_visiveis,
    consentimento_permite,
    pode_ver_aluno,
    to_object_id,
)
from app.Utils.decorators import token_required
from app.Utils.responses import (
    dados_invalidos,
    erro,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

iot_bp = Blueprint('iot_bp', __name__)

alert_model = Alert()
registro_model = RegistroIoT()


def _api_key_valida(chave_recebida):
    """Compara a API key em tempo constante."""
    esperada = os.getenv('SECRET_API_KEY')
    if not esperada or not chave_recebida:
        return False
    return hmac.compare_digest(str(chave_recebida), str(esperada))


@iot_bp.route('/data', methods=['POST'])
def receber_dados_iot():
    """Recebe dados de dispositivos IoT. Protegido por X-API-Key."""
    try:
        if not _api_key_valida(request.headers.get('X-API-Key')):
            return erro('API Key invalida ou ausente', 401)

        data = request.get_json(silent=True)
        if not data or 'dispositivo_id' not in data or 'dados_biometricos' not in data:
            return dados_invalidos(
                'Dados ausentes: dispositivo_id e dados_biometricos sao obrigatorios'
            )

        dispositivo_oid = to_object_id(data['dispositivo_id'])
        if dispositivo_oid is None:
            return dados_invalidos('ID do dispositivo invalido')

        dados_biometricos = data['dados_biometricos']
        if not isinstance(dados_biometricos, dict) or not dados_biometricos:
            return dados_invalidos('Dados biometricos devem ser um objeto nao vazio')

        dispositivo = mongo.db.dispositivos.find_one({'_id': dispositivo_oid})
        if not dispositivo:
            return nao_encontrado('Dispositivo nao registrado')

        aluno_id = dispositivo.get('aluno_id')
        if not aluno_id:
            return dados_invalidos('Dispositivo nao associado a nenhum aluno')

        # Base legal: sem consentimento vigente do responsavel para coleta
        # biometrica, o dado e descartado na porta de entrada. Revogar tem
        # efeito imediato (LGPD art. 8o, §5o).
        if not consentimento_permite(aluno_id, COLETA_BIOMETRICA):
            logger.info(
                'Leitura descartada: sem consentimento biometrico para o aluno %s',
                aluno_id,
            )
            return erro(
                'Coleta biometrica nao autorizada para este aluno', 403,
                motivo='consentimento_ausente',
            )

        resultado = registro_model.create({
            'aluno_id': aluno_id,
            'dispositivo_id': dispositivo_oid,
            'dados_biometricos': dados_biometricos,
            'processado': False,
        })

        mongo.db.dispositivos.update_one(
            {'_id': dispositivo_oid},
            {'$set': {
                'ultima_conexao': datetime.datetime.utcnow(),
                'status': 'ativo',
                'ultimo_registro_id': resultado.inserted_id,
            }},
        )

        return sucesso(
            message='Dados recebidos com sucesso!',
            status_code=201,
            registro_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao salvar dados IoT')


@iot_bp.route('/dispositivos/<aluno_id>', methods=['GET'])
@token_required
def listar_dispositivos_aluno(current_user, aluno_id):
    """Lista os dispositivos de um aluno."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado aos dados deste aluno')

        dispositivos = []
        for d in mongo.db.dispositivos.find({'aluno_id': aluno_oid}):
            ultima = d.get('ultima_conexao')
            dispositivos.append({
                '_id': str(d['_id']),
                'aluno_id': str(d['aluno_id']),
                'status': d.get('status', 'desconhecido'),
                'ultima_conexao': ultima.isoformat() if ultima else None,
            })

        return sucesso(data=dispositivos, dispositivos=dispositivos)

    except Exception as e:
        return erro_interno(e, 'ao buscar dispositivos')


@iot_bp.route('/registros/<aluno_id>', methods=['GET'])
@token_required
def listar_registros_aluno(current_user, aluno_id):
    """Lista as leituras biometricas de um aluno (paginado)."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado aos dados deste aluno')

        limite = max(1, min(request.args.get('limite', 50, type=int) or 50, 500))
        pagina = max(1, request.args.get('pagina', 1, type=int) or 1)

        registros = registro_model.find_by_aluno(
            aluno_oid, limite=limite, pular=(pagina - 1) * limite
        )
        serializados = [RegistroIoT.serializar(r) for r in registros]

        return sucesso(
            data=serializados,
            registros=serializados,
            pagina=pagina,
            limite=limite,
            total=registro_model.count_by_aluno(aluno_oid),
        )

    except Exception as e:
        return erro_interno(e, 'ao buscar registros')


@iot_bp.route('/crisis-alerts', methods=['GET'])
@token_required
def get_crisis_alerts(current_user):
    """Alertas de crise recentes dos alunos visiveis ao usuario.

    Le da colecao 'alerts', que e onde o alert_monitor grava as crises
    detectadas pelo modelo. Antes esta rota consultava 'registros_iot'
    filtrando por heart_rate/eda, campos que o pipeline nunca gravou.
    """
    try:
        alunos_ids = alunos_visiveis(current_user)
        if not alunos_ids:
            return sucesso(data=[], alerts=[], count=0)

        minutos = max(1, min(request.args.get('minutos', 30, type=int) or 30, 1440))
        desde = datetime.datetime.utcnow() - datetime.timedelta(minutes=minutos)

        alertas = alert_model.find_by_alunos(alunos_ids, desde=desde)

        nomes = {
            u['_id']: u.get('nome', 'Desconhecido')
            for u in mongo.db.users.find(
                {'_id': {'$in': list(alunos_ids)}}, {'nome': 1}
            )
        }

        resultado = []
        for alerta in alertas:
            serializado = Alert.serializar(alerta)
            serializado['student_id'] = serializado['aluno_id']
            serializado['student_name'] = nomes.get(alerta['aluno_id'], 'Desconhecido')
            serializado['heart_rate'] = serializado['bpm']
            serializado['eda'] = serializado['gsr']
            serializado['timestamp'] = serializado['data_hora']
            resultado.append(serializado)

        return sucesso(data=resultado, alerts=resultado, count=len(resultado))

    except Exception as e:
        return erro_interno(e, 'ao buscar alertas de crise')


@iot_bp.route('/alerts/<alert_id>/resolve', methods=['PUT'])
@token_required
def resolver_alerta(current_user, alert_id):
    """Marca um alerta de crise como resolvido."""
    try:
        alerta = alert_model.find_by_id(alert_id)
        if not alerta:
            return nao_encontrado('Alerta nao encontrado')

        if not pode_ver_aluno(current_user, alerta.get('aluno_id')):
            return nao_autorizado('Acesso nao autorizado a este alerta')

        alert_model.marcar_resolvido(alert_id, current_user['_id'])
        return sucesso(message='Alerta marcado como resolvido')

    except Exception as e:
        return erro_interno(e, 'ao resolver alerta')


@iot_bp.route('/dispositivos', methods=['POST'])
@token_required
def registrar_dispositivo(current_user):
    """Registra uma pulseira e a associa a um aluno."""
    try:
        from app.Utils.roles import normalizar_tipo, PROFESSOR, ADMIN

        if normalizar_tipo(current_user.get('tipo')) not in (PROFESSOR, ADMIN):
            return nao_autorizado('Apenas professores podem registrar dispositivos')

        data = request.get_json(silent=True) or {}
        aluno_oid = to_object_id(data.get('aluno_id'))
        if aluno_oid is None:
            return dados_invalidos('aluno_id e obrigatorio e deve ser valido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado a este aluno')

        documento = {
            'aluno_id': aluno_oid,
            'status': 'ativo',
            'ultima_conexao': None,
            'registrado_em': datetime.datetime.utcnow(),
            'registrado_por': current_user['_id'],
        }
        if data.get('dispositivo_id'):
            dispositivo_oid = to_object_id(data['dispositivo_id'])
            if dispositivo_oid is None:
                return dados_invalidos('dispositivo_id invalido')
            documento['_id'] = dispositivo_oid

        resultado = mongo.db.dispositivos.insert_one(documento)
        return sucesso(
            message='Dispositivo registrado com sucesso',
            status_code=201,
            dispositivo_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao registrar dispositivo')
