"""
Modelo de alertas de crise e de registros biometricos brutos.

Contrato de dados do pipeline (camada 3 -> camada 4):

    colecao 'alerts'         -> alertas gerados pelo modelo de ML
    colecao 'registros_iot'  -> data lake de leituras biometricas

Campos canonicos de um alerta:
    aluno_id            ObjectId  (NAO 'student_id')
    dispositivo_id      ObjectId | None
    data_hora           datetime (UTC)
    dados_biometricos   {bpm, gsr, movement_score}
    severity            'medium' | 'high'
    motivo              str
    resolvido           bool
    modelo_validado     bool — ver nota abaixo

Antes desta padronizacao o alert_monitor gravava 'aluno_id' enquanto o
dashboard consultava 'student_id', e os dados brutos iam para 'iot_raw_data'
enquanto a API lia 'registros_iot'. O resultado era que nenhum alerta
detectado pelo modelo chegava ao professor.

ADR-010 — 'modelo_validado' (guarda-corpo, nao correcao do modelo):
scripts/utils/train_model.py treina com dado SINTETICO (ruido de 25%, 8% dos
rotulos invertidos de proposito) e LIMIAR_BPM_ALTO=130 marca severidade
maxima — 130 bpm e uma crianca de 7 anos no recreio, nao necessariamente uma
crise. Nao ha, hoje, validacao clinica de nenhum dos dois. Nao inventamos um
novo limiar aqui (decisao clinica que nao cabe a este time) — em vez disso,
os limiares viram configuraveis por ambiente (ajustaveis sem deploy assim
que houver validacao real) e MODELO_VALIDADO fica False de proposito,
gravado em CADA alerta. Isso transforma o aviso da ADR de comentario que
ninguem le as 2h da manha em campo visivel no proprio alerta, que a UI pode
usar para avisar quem le que a severidade ainda nao e' clinicamente
confiavel. Mesmos limiares e mesma flag espelhados em alert_monitor.py —
ver test_severidade_coincide_com_a_do_modelo_de_alertas, que existe
justamente para pegar essa duplicacao saindo de sincronia.
"""

import datetime
import os

from bson.objectid import ObjectId

from app import mongo

# Limiares clinicos usados para classificar a severidade do alerta —
# configuraveis por ambiente, nao hardcoded, para permitir ajuste sem
# deploy assim que houver validacao clinica real.
LIMIAR_BPM_ALTO = float(os.environ.get('LIMIAR_BPM_ALTO', 130))
LIMIAR_GSR_ALTO = float(os.environ.get('LIMIAR_GSR_ALTO', 4.0))

# Continua False ate alguem validar o modelo/limiares com dado real e
# mudar isto conscientemente — nunca inferir "validado" de nenhuma outra
# condicao (ex.: limiar customizado != limiar validado).
MODELO_VALIDADO = os.environ.get('MODELO_RISCO_VALIDADO', 'false').strip().lower() == 'true'


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


def classificar_severidade(dados_biometricos):
    """Classifica a severidade a partir dos dados biometricos."""
    dados = dados_biometricos or {}
    bpm = dados.get('bpm') or 0
    gsr = dados.get('gsr') or 0
    if bpm > LIMIAR_BPM_ALTO or gsr > LIMIAR_GSR_ALTO:
        return 'high'
    return 'medium'


def normalizar_biometria(dados):
    """Normaliza nomes de campos vindos de fontes distintas.

    A pulseira envia bpm/gsr/movement_score; payloads antigos do dashboard
    usavam heart_rate/eda. Aqui tudo converge para o formato canonico.
    """
    dados = dados or {}
    return {
        'bpm': dados.get('bpm', dados.get('heart_rate', 0)),
        'gsr': dados.get('gsr', dados.get('eda', 0)),
        'movement_score': dados.get('movement_score', dados.get('movement', 0)),
    }


class Alert:
    def create_alert(self, alert_data):
        """Registra um alerta de crise no formato canonico."""
        aluno_oid = _to_object_id(alert_data.get('aluno_id'))
        if aluno_oid is None:
            raise ValueError('aluno_id invalido ao criar alerta')

        dados_bio = normalizar_biometria(alert_data.get('dados_biometricos'))

        documento = {
            'aluno_id': aluno_oid,
            'dispositivo_id': _to_object_id(alert_data.get('dispositivo_id')),
            'data_hora': alert_data.get('data_hora') or datetime.datetime.utcnow(),
            'dados_biometricos': dados_bio,
            'severity': alert_data.get('severity') or classificar_severidade(dados_bio),
            'motivo': alert_data.get('motivo', 'Predicao do Modelo de ML'),
            'ml_confidence': alert_data.get('ml_confidence'),
            'resolvido': False,
            'modelo_validado': MODELO_VALIDADO,
        }
        return mongo.db.alerts.insert_one(documento)

    def find_by_alunos(self, alunos_ids, desde=None, limite=None):
        """Alertas de um conjunto de alunos, mais recentes primeiro."""
        oids = [o for o in (_to_object_id(i) for i in alunos_ids) if o is not None]
        if not oids:
            return []

        query = {'aluno_id': {'$in': oids}}
        if desde:
            query['data_hora'] = {'$gte': desde}

        cursor = mongo.db.alerts.find(query).sort('data_hora', -1)
        if limite:
            cursor = cursor.limit(limite)
        return list(cursor)

    def find_by_aluno(self, aluno_id, desde=None, ordem=-1):
        """Historico de alertas de um aluno."""
        oid = _to_object_id(aluno_id)
        if oid is None:
            return []

        query = {'aluno_id': oid}
        if desde:
            query['data_hora'] = {'$gte': desde}

        return list(mongo.db.alerts.find(query).sort('data_hora', ordem))

    def marcar_resolvido(self, alert_id, resolvido_por):
        oid = _to_object_id(alert_id)
        if oid is None:
            return None
        return mongo.db.alerts.update_one(
            {'_id': oid},
            {'$set': {
                'resolvido': True,
                'resolvido_por': _to_object_id(resolvido_por),
                'resolvido_em': datetime.datetime.utcnow(),
            }},
        )

    def find_by_id(self, alert_id):
        oid = _to_object_id(alert_id)
        if oid is None:
            return None
        return mongo.db.alerts.find_one({'_id': oid})

    @staticmethod
    def serializar(alerta):
        """Converte um alerta para o formato de resposta da API."""
        dados_bio = normalizar_biometria(alerta.get('dados_biometricos'))
        data_hora = alerta.get('data_hora')
        return {
            '_id': str(alerta.get('_id')),
            'aluno_id': str(alerta.get('aluno_id')),
            'data_hora': data_hora.isoformat() if data_hora else None,
            'bpm': dados_bio['bpm'],
            'gsr': dados_bio['gsr'],
            'movement_score': dados_bio['movement_score'],
            'severity': alerta.get('severity', 'medium'),
            'motivo': alerta.get('motivo', ''),
            'resolvido': alerta.get('resolvido', False),
            'ml_confidence': alerta.get('ml_confidence'),
            # False tambem para alertas antigos, gravados antes deste campo
            # existir — o default seguro e' "nao confiar", nao "assumir ok".
            'modelo_validado': alerta.get('modelo_validado', False),
        }


class RegistroIoT:
    """Data lake de leituras biometricas (colecao 'registros_iot')."""

    def create(self, registro):
        aluno_oid = _to_object_id(registro.get('aluno_id'))
        if aluno_oid is None:
            raise ValueError('aluno_id invalido ao gravar registro IoT')

        documento = {
            'aluno_id': aluno_oid,
            'dispositivo_id': _to_object_id(registro.get('dispositivo_id')),
            'data_hora': registro.get('data_hora') or datetime.datetime.utcnow(),
            'dados_biometricos': normalizar_biometria(registro.get('dados_biometricos')),
            'processado': registro.get('processado', False),
        }
        # Metadados opcionais vindos da pulseira
        for campo in ('bateria', 'timestamp_pulseira_sp', 'timestamp_original_unix'):
            if campo in registro:
                documento[campo] = registro[campo]

        return mongo.db.registros_iot.insert_one(documento)

    def find_by_aluno(self, aluno_id, limite=50, pular=0):
        oid = _to_object_id(aluno_id)
        if oid is None:
            return []
        return list(
            mongo.db.registros_iot.find({'aluno_id': oid})
            .sort('data_hora', -1)
            .skip(pular)
            .limit(limite)
        )

    def count_by_aluno(self, aluno_id):
        oid = _to_object_id(aluno_id)
        if oid is None:
            return 0
        return mongo.db.registros_iot.count_documents({'aluno_id': oid})

    @staticmethod
    def serializar(registro):
        data_hora = registro.get('data_hora')
        return {
            '_id': str(registro.get('_id')),
            'aluno_id': str(registro.get('aluno_id')),
            'dispositivo_id': str(registro.get('dispositivo_id')) if registro.get('dispositivo_id') else None,
            'data_hora': data_hora.isoformat() if data_hora else None,
            'dados_biometricos': normalizar_biometria(registro.get('dados_biometricos')),
            'bateria': registro.get('bateria'),
        }
