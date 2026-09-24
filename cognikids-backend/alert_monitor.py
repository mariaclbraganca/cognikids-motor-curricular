"""
Camada 3 (Inteligencia): consome a fila Redis, executa a inferencia do
Random Forest e grava o resultado no MongoDB.

Contrato de saida (consumido pela camada 4 / dashboard):
    registros_iot -> toda leitura recebida (data lake)
    alerts        -> apenas as leituras classificadas como crise

Ambas as colecoes usam 'aluno_id' como chave do aluno. Esse alinhamento e o
que permite ao dashboard do professor enxergar os alertas do modelo.
"""

import datetime
import json
import os
import time

import joblib
import pandas as pd
import redis
from bson.objectid import ObjectId
from pymongo import MongoClient

REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://db:27017/cognikidsDB')
MODEL_PATH = os.getenv('MODEL_PATH', 'model.joblib')
FILA = os.getenv('IOT_QUEUE', 'iot_queue')

# Limiares de severidade e flag de validacao — espelham app/Models/alert_model.py
# de proposito (mesmo ambiente, mesmo valor). ADR-010: nenhum dos dois foi
# validado clinicamente ainda; ver a nota longa em alert_model.py.
LIMIAR_BPM_ALTO = float(os.getenv('LIMIAR_BPM_ALTO', 130))
LIMIAR_GSR_ALTO = float(os.getenv('LIMIAR_GSR_ALTO', 4.0))
MODELO_VALIDADO = os.getenv('MODELO_RISCO_VALIDADO', 'false').strip().lower() == 'true'

# Recursos abertos em conectar(), nao no import: assim o modulo pode ser
# importado por testes sem exigir Redis, Mongo e o modelo treinado no ar.
redis_client = None
db = None
model = None
col_registros = None
col_alerts = None


def conectar():
    """Abre conexoes e carrega o modelo. Encerra o processo se algo falhar."""
    global redis_client, db, model, col_registros, col_alerts

    print("Iniciando o Consumidor (alert_monitor.py)...")

    try:
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True
        )
        redis_client.ping()
        print("[OK] Consumidor: Conectado ao Redis.")
    except Exception as e:
        print(f"[ERRO] Consumidor: Falha ao conectar ao Redis: {e}")
        raise SystemExit(1)

    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client.get_default_database()
        db.command('ping')
        print("[OK] Consumidor: Conectado ao MongoDB.")
    except Exception as e:
        print(f"[ERRO] Consumidor: Falha ao conectar ao MongoDB: {e}")
        raise SystemExit(1)

    try:
        model = joblib.load(MODEL_PATH)
        print(f"[OK] Consumidor: Modelo '{MODEL_PATH}' carregado com sucesso.")
    except FileNotFoundError:
        print(f"[ERRO] Consumidor: '{MODEL_PATH}' nao encontrado. "
              f"Execute 'python scripts/utils/train_model.py' primeiro.")
        raise SystemExit(1)
    except Exception as e:
        print(f"[ERRO] Consumidor: Erro ao carregar '{MODEL_PATH}': {e}")
        raise SystemExit(1)

    col_registros = db.registros_iot
    col_alerts = db.alerts


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


def classificar_severidade(dados_bio):
    bpm = dados_bio.get('bpm') or 0
    gsr = dados_bio.get('gsr') or 0
    return 'high' if (bpm > LIMIAR_BPM_ALTO or gsr > LIMIAR_GSR_ALTO) else 'medium'


def processar_mensagem(raw_data):
    """Processa uma mensagem da fila: grava o dado bruto, infere e alerta.

    Args:
        raw_data (str): Dados em JSON string vindos do Redis.
    """
    try:
        data = json.loads(raw_data)
    except json.JSONDecodeError:
        print("     Erro: Dado mal formatado recebido do Redis.")
        return

    aluno_oid = _to_object_id(data.get('aluno_id'))
    if aluno_oid is None:
        print(f"     REJEITADO: aluno_id invalido ({data.get('aluno_id')})")
        return

    dispositivo_oid = _to_object_id(data.get('dispositivo_id'))
    dados_bio_brutos = data.get('dados_biometricos', {}) or {}

    # Formato canonico das features
    dados_bio = {
        'bpm': dados_bio_brutos.get('bpm', dados_bio_brutos.get('heart_rate', 0)) or 0,
        'gsr': dados_bio_brutos.get('gsr', dados_bio_brutos.get('eda', 0)) or 0,
        'movement_score': dados_bio_brutos.get(
            'movement_score', dados_bio_brutos.get('movement', 0)
        ) or 0,
    }

    agora = datetime.datetime.utcnow()

    try:
        # 1. Data lake: grava toda leitura em registros_iot
        registro = {
            'aluno_id': aluno_oid,
            'dispositivo_id': dispositivo_oid,
            'data_hora': agora,
            'dados_biometricos': dados_bio,
            'processado': True,
            'origem': 'mqtt',
        }
        for campo in ('bateria', 'timestamp_pulseira_sp', 'timestamp_original_unix'):
            if campo in data:
                registro[campo] = data[campo]
        col_registros.insert_one(registro)

        # 2. Inferencia do modelo
        features = pd.DataFrame([{
            'bpm': dados_bio['bpm'],
            'gsr': dados_bio['gsr'],
            'movement_score': dados_bio['movement_score'],
        }])
        previsao = model.predict(features)[0]

        # Confianca da predicao, quando o estimador expoe probabilidades
        confianca = None
        if hasattr(model, 'predict_proba'):
            try:
                confianca = float(max(model.predict_proba(features)[0]))
            except Exception:
                confianca = None

        # 3. Alerta apenas quando ha crise detectada
        if int(previsao) == 1:
            print(f"[ALERTA] CRISE DETECTADA - Aluno: {aluno_oid}, BPM: {dados_bio['bpm']}")
            col_alerts.insert_one({
                'aluno_id': aluno_oid,
                'dispositivo_id': dispositivo_oid,
                'data_hora': agora,
                'dados_biometricos': dados_bio,
                'severity': classificar_severidade(dados_bio),
                'motivo': 'Predicao do Modelo de ML',
                'ml_confidence': confianca,
                'resolvido': False,
                'modelo_validado': MODELO_VALIDADO,
            })
        else:
            print(f"[OK] Dados normais - Aluno: {aluno_oid}, BPM: {dados_bio['bpm']}")

    except Exception as e:
        print(f"     Erro ao processar mensagem: {e}")


def iniciar_consumidor():
    """Loop principal: aguarda dados na fila Redis de forma bloqueante."""
    conectar()
    print(f"Aguardando dados na fila '{FILA}'...")
    while True:
        try:
            item_enfileirado = redis_client.brpop(FILA, 0)
            if not item_enfileirado:
                continue
            processar_mensagem(item_enfileirado[1])

        except redis.exceptions.ConnectionError:
            print("[ERRO] Perda de conexao com o Redis. Tentando reconectar em 5s...")
            time.sleep(5)
        except Exception as e:
            print(f"[ERRO] Erro critico no loop do consumidor: {e}")
            time.sleep(5)


if __name__ == "__main__":
    iniciar_consumidor()
