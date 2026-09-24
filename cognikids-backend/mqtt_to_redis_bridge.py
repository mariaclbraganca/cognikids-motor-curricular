import paho.mqtt.client as mqtt
import redis
import json
import time
import os
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime
import pytz  # Para conversão de timezone

# Configuracao de timezone para Sao Paulo
TZ_SAO_PAULO = pytz.timezone('America/Sao_Paulo')

MONGO_URI = os.getenv('MONGO_URI', 'mongodb://db:27017/cognikidsDB')
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# As conexoes sao abertas em conectar(), nao no import: assim o modulo pode
# ser importado (por testes ou ferramentas) sem exigir Mongo e Redis no ar.
db = None
redis_client = None


def conectar():
    """Abre as conexoes com MongoDB e Redis. Encerra o processo se falhar."""
    global db, redis_client

    try:
        mongo_client = MongoClient(MONGO_URI)
        db = mongo_client.get_default_database()
        db.command('ping')
        print(f"[OK] Ponte: Conectado ao MongoDB (Servico: {MONGO_URI})")
    except Exception as e:
        print(f"[ERRO] Ponte: Falha ao conectar ao MongoDB: {e}")
        raise SystemExit(1)

    try:
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, decode_responses=True
        )
        redis_client.ping()
        print(f"[OK] Ponte: Conectado ao Redis (Servico: '{REDIS_HOST}')")
    except Exception as e:
        print(f"[ERRO] Ponte: Falha ao conectar ao Redis: {e}")
        raise SystemExit(1)


# --- Lógica do MQTT ---
MQTT_BROKER_HOST = os.getenv('MQTT_BROKER_HOST', 'mosquitto')
MQTT_PORT = int(os.getenv('MQTT_PORT', 1883))
MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'cognikids/iot/data')

# Teto da fila Redis. Sem limite, uma queda prolongada do consumidor faria o
# "buffer elastico" crescer ate esgotar a memoria do Redis.
FILA = os.getenv('IOT_QUEUE', 'iot_queue')
FILA_MAX = int(os.getenv('IOT_QUEUE_MAX', 50000))


# Finalidade de consentimento exigida para a coleta da pulseira.
# Espelha app/Models/consent_model.py; a ponte roda fora do contexto Flask
# e por isso consulta o MongoDB diretamente.
CONSENT_COLETA_BIOMETRICA = 'coleta_biometrica'


def _primeiro_valido(*valores):
    """Retorna o primeiro valor que nao seja None.

    Diferente de `or`, preserva zeros: `0 or 5` devolve 5, mas
    `_primeiro_valido(0, 5)` devolve 0 — que e o comportamento correto para
    leituras de sensor, onde zero e uma medida legitima.
    """
    for valor in valores:
        if valor is not None:
            return valor
    return None


def consentimento_biometrico_valido(aluno_id):
    """Ha consentimento vigente para coletar dados biometricos deste aluno?

    Nega por padrao: sem documento de consentimento, nao ha base legal.
    """
    documento = db.consents.find_one({'aluno_id': aluno_id}, {'finalidades': 1})
    if not documento:
        return False
    return bool(documento.get('finalidades', {}).get(CONSENT_COLETA_BIOMETRICA))

def transformar_payload_pulseira(data):
    """
    Transforma o payload da pulseira M5Stack para o formato padrao do sistema.
    
    Aceita dois formatos de entrada:
    
    Formato 1 - Abreviado (pulseira M5Stack):
        - id: Identificador do dispositivo
        - bpm: Batimentos por minuto
        - mov: Score de movimento
        - ts: Timestamp Unix
        - batt: Nivel de bateria
    
    Formato 2 - Completo:
        - device_id: Identificador do dispositivo
        - bpm: Batimentos por minuto
        - movement: Score de movimento
        - raw_sensor: Dado bruto do sensor
        - timestamp: Timestamp Unix
    
    Args:
        data (dict): Payload recebido da pulseira.
    
    Returns:
        dict: Payload padronizado para o sistema CogniKids.
    """
    # Usa _primeiro_valido (nao 'or') porque 0 e um valor legitimo:
    # movimento zero significa aluno imovel, que e um sinal clinico relevante.
    device_id = _primeiro_valido(data.get('id'), data.get('device_id'))
    timestamp_unix = _primeiro_valido(data.get('ts'), data.get('timestamp'), time.time())
    movement = _primeiro_valido(data.get('mov'), data.get('movement'), 0)
    bateria = _primeiro_valido(data.get('batt'), data.get('bateria'), 100)

    # O sensor GSR pode nao estar presente na pulseira. Quando ausente o valor
    # e None (e nao 0), para nao simular leitura de repouso: 0 e um valor
    # valido de GSR e faria o modelo tratar ausencia como sinal.
    gsr = _primeiro_valido(data.get('gsr'), data.get('eda'), None)

    # Converte timestamp Unix para DateTime no fuso de São Paulo
    dt_utc = datetime.datetime.utcfromtimestamp(timestamp_unix)
    dt_sp = pytz.utc.localize(dt_utc).astimezone(TZ_SAO_PAULO)

    # Monta o payload no formato esperado pelo sistema
    return {
        'dispositivo_id': device_id,
        'dados_biometricos': {
            'bpm': _primeiro_valido(data.get('bpm'), 0),
            'gsr': gsr,
            'movement_score': movement,
            'raw_ppg': _primeiro_valido(data.get('raw_sensor'), 0)
        },
        'timestamp_pulseira_sp': dt_sp.isoformat(),
        'timestamp_original_unix': timestamp_unix,
        'bateria': bateria
    }

def on_connect(client, userdata, flags, rc):
    """
    Callback executado apos conexao com o Broker MQTT.
    
    Args:
        client: Instancia do cliente MQTT.
        userdata: Dados do usuario definidos no cliente.
        flags: Flags de resposta do broker.
        rc: Codigo de resultado da conexao.
    """
    if rc == 0:
        print(f"[OK] Ponte: Conectado ao MQTT Broker '{MQTT_BROKER_HOST}'")
        client.subscribe(MQTT_TOPIC)
        print(f"     Inscrito no topico '{MQTT_TOPIC}'")
    else:
        print(f"[ERRO] Ponte: Falha ao conectar ao MQTT Broker, codigo: {rc}")

def on_message(client, userdata, msg):
    """
    Callback executado ao receber uma mensagem MQTT.
    
    Processa dados biometricos recebidos da pulseira ou simulador,
    valida o dispositivo e enfileira no Redis para processamento.
    
    Args:
        client: Instancia do cliente MQTT.
        userdata: Dados do usuario definidos no cliente.
        msg: Mensagem recebida contendo topico e payload.
    """
    try:
        payload_str = msg.payload.decode('utf-8')
        print(f"\nRecebido de MQTT: {payload_str}")
        
        data = json.loads(payload_str)
        
        # Detecta e transforma payload da pulseira M5Stack para formato padrao
        is_pulseira_real = ('id' in data or 'device_id' in data) and 'bpm' in data
        if is_pulseira_real:
            print("     Payload de pulseira M5Stack detectado. Transformando...")
            data = transformar_payload_pulseira(data)
            print(f"     Payload transformado: {json.dumps(data, default=str)}")
        
        # Validacao do ID do dispositivo
        dispositivo_id = data.get('dispositivo_id')
        if not dispositivo_id or not ObjectId.is_valid(dispositivo_id):
            print(f"     REJEITADO: ID de dispositivo invalido ({dispositivo_id})")
            return

        # Verifica existencia do dispositivo e obtem o ID do aluno associado
        dispositivo = db.dispositivos.find_one({"_id": ObjectId(dispositivo_id)})
        
        if not dispositivo:
            print(f"     REJEITADO: Dispositivo {dispositivo_id} nao registrado")
            return
            
        aluno_id = dispositivo.get('aluno_id')
        if not aluno_id:
            print(f"     REJEITADO: Dispositivo {dispositivo_id} nao associado a um aluno")
            return

        # Base legal (LGPD): sem consentimento vigente do responsavel para
        # coleta biometrica, a leitura e descartada aqui — antes de entrar
        # na fila. Revogar o consentimento tem efeito imediato.
        if not consentimento_biometrico_valido(aluno_id):
            print(f"     REJEITADO: Sem consentimento biometrico para o aluno {aluno_id}")
            return

        # Enriquece o payload com dados complementares
        data['aluno_id'] = str(aluno_id)
        data['dispositivo_id'] = str(dispositivo_id)
        data['timestamp_bridge_utc'] = datetime.datetime.utcnow().isoformat()
        
        # Enfileira no Redis e aplica o teto da fila na mesma transacao:
        # LTRIM descarta as leituras mais antigas se o consumidor nao acompanhar.
        pipe = redis_client.pipeline()
        pipe.lpush(FILA, json.dumps(data))
        pipe.ltrim(FILA, 0, FILA_MAX - 1)
        pipe.execute()
        print(f"     VALIDADO: Aluno {aluno_id}. Dados enfileirados no Redis.")

    except json.JSONDecodeError:
        print("     REJEITADO: Payload MQTT nao e um JSON valido")
    except Exception as e:
        print(f"     ERRO na Ponte (on_message): {e}")

# Loop Principal da Ponte MQTT-Redis
def iniciar_ponte():
    """
    Inicializa e executa o loop principal da ponte MQTT-Redis.
    
    Estabelece conexao com o broker MQTT e aguarda mensagens
    de forma bloqueante.
    """
    print("Iniciando a Ponte MQTT-Redis-Bridge...")
    conectar()

    mqtt_client = mqtt.Client(client_id="cognikids-bridge")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    # Aguarda disponibilidade do broker MQTT
    connected = False
    while not connected:
        try:
            mqtt_client.connect(MQTT_BROKER_HOST, 1883, 60)
            connected = True
        except Exception as e:
            print(f"Aguardando MQTT Broker '{MQTT_BROKER_HOST}'... (Erro: {e})")
            time.sleep(5)
            
    # Bloqueia o script, ouvindo para sempre
    mqtt_client.loop_forever()

if __name__ == "__main__":
    iniciar_ponte()