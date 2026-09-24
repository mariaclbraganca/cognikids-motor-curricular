"""
Popula dados de teste do pipeline IoT (data lake + alertas).

Simula o fluxo MQTT -> Redis -> alert_monitor.py -> MongoDB, gravando no
mesmo formato canonico que o consumidor real usa:

    registros_iot -> toda leitura biometrica ('aluno_id', 'data_hora')
    alerts        -> apenas as crises ('aluno_id', 'severity', 'resolvido')

Os alunos sao resolvidos dinamicamente pelo banco: a versao anterior tinha
ObjectIds fixos de uma instalacao especifica e nao funcionava em outra base.

Uso:
    python scripts/seeds/popular_dados_teste.py
"""

import argparse
import datetime
import os
import random
import sys

from bson.objectid import ObjectId
from pymongo import MongoClient

TIPOS_ESTUDANTE = ['estudante', 'aluno', 'student']

LIMIAR_BPM_ALTO = 130
LIMIAR_GSR_ALTO = 4.0


def gerar_dados_biometricos(tipo='normal'):
    """Gera uma leitura sintetica. tipo: 'normal', 'estresse' ou 'crise'."""
    if tipo == 'normal':
        return {
            'bpm': random.randint(70, 100),
            'gsr': round(random.uniform(0.5, 1.0), 2),
            'movement_score': round(random.uniform(0.3, 1.0), 2),
        }
    if tipo == 'estresse':
        return {
            'bpm': random.randint(100, 130),
            'gsr': round(random.uniform(1.0, 1.8), 2),
            'movement_score': round(random.uniform(1.0, 2.0), 2),
        }
    return {
        'bpm': random.randint(130, 165),
        'gsr': round(random.uniform(2.0, 5.0), 2),
        'movement_score': round(random.uniform(2.0, 3.5), 2),
    }


def classificar_severidade(dados_bio):
    if dados_bio['bpm'] > LIMIAR_BPM_ALTO or dados_bio['gsr'] > LIMIAR_GSR_ALTO:
        return 'high'
    return 'medium'


def obter_dispositivo(db, aluno_id):
    """Devolve o dispositivo do aluno, criando um se necessario."""
    dispositivo = db.dispositivos.find_one({'aluno_id': aluno_id})
    if dispositivo:
        return dispositivo['_id']

    return db.dispositivos.insert_one({
        'aluno_id': aluno_id,
        'status': 'ativo',
        'ultima_conexao': datetime.datetime.utcnow(),
    }).inserted_id


def popular_aluno(db, aluno, n_leituras, n_crises):
    """Gera leituras para um aluno; as ultimas `n_crises` sao crises."""
    aluno_id = aluno['_id']
    dispositivo_id = obter_dispositivo(db, aluno_id)

    agora = datetime.datetime.utcnow()
    timestamps = [
        agora - datetime.timedelta(minutes=i) for i in range(n_leituras, 0, -1)
    ]

    crises = 0
    for i, ts in enumerate(timestamps):
        eh_crise = i >= (n_leituras - n_crises)
        dados_bio = gerar_dados_biometricos('crise' if eh_crise else 'normal')

        # 1. Data lake — mesma colecao/campos que a API consulta
        db.registros_iot.insert_one({
            'aluno_id': aluno_id,
            'dispositivo_id': dispositivo_id,
            'data_hora': ts,
            'dados_biometricos': dados_bio,
            'processado': True,
            'origem': 'seed',
        })

        # 2. Alerta apenas quando ha crise
        if eh_crise:
            db.alerts.insert_one({
                'aluno_id': aluno_id,
                'dispositivo_id': dispositivo_id,
                'data_hora': ts,
                'dados_biometricos': dados_bio,
                'severity': classificar_severidade(dados_bio),
                'motivo': 'Predicao do Modelo de ML',
                'ml_confidence': round(random.uniform(0.75, 0.98), 2),
                'resolvido': False,
            })
            crises += 1
            print(f"   [CRISE] {aluno.get('nome')}: BPM={dados_bio['bpm']}, "
                  f"GSR={dados_bio['gsr']} as {ts.strftime('%H:%M:%S')}")

    return crises


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mongo-uri',
                        default=os.getenv('MONGO_URI', 'mongodb://localhost:27017/cognikidsDB'))
    parser.add_argument('--leituras', type=int, default=10,
                        help='leituras por aluno (padrao: 10)')
    parser.add_argument('--crises', type=int, default=2,
                        help='quantas das ultimas leituras sao crises (padrao: 2)')
    parser.add_argument('--alunos', type=int, default=2,
                        help='quantos alunos popular (padrao: 2)')
    parser.add_argument('--manter', action='store_true',
                        help='nao apagar os dados existentes')
    args = parser.parse_args()

    print("\n=== POPULANDO DADOS DE TESTE (Data Lake + Alertas) ===\n")

    db = MongoClient(args.mongo_uri).get_default_database()

    alunos = list(db.users.find({'tipo': {'$in': TIPOS_ESTUDANTE}}).limit(args.alunos))
    if not alunos:
        print("ERRO: Nenhum estudante encontrado no banco.")
        print("      Cadastre alunos primeiro (POST /api/register ou populate_mongo.py).")
        return 1

    if not args.manter:
        db.registros_iot.delete_many({})
        db.alerts.delete_many({})
        print("Colecoes limpas (registros_iot, alerts)\n")

    total_crises = 0
    for i, aluno in enumerate(alunos):
        # O primeiro aluno recebe crises; os demais ficam estaveis, para a
        # demo mostrar os dois cenarios lado a lado.
        crises = args.crises if i == 0 else 0
        print(f"Gerando {args.leituras} leituras para {aluno.get('nome')} "
              f"({crises} crises)...")
        total_crises += popular_aluno(db, aluno, args.leituras, crises)

    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    print(f"Data Lake (registros_iot): {db.registros_iot.count_documents({})} registros")
    print(f"Alertas (alerts):          {db.alerts.count_documents({})} crises")
    print(f"Alunos populados:          {len(alunos)}")
    print("\nOK: Dados populados. Eles ja aparecem em:")
    print("   GET /api/teachers/crisis_alerts")
    print("   GET /api/iot/crisis-alerts\n")
    return 0


if __name__ == '__main__':
    sys.exit(main())
