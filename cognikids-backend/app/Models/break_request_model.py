"""
Pedido de pausa.

E a funcionalidade que materializa o pilar 'Autonomy' do framework DAD: em
vez de o sistema apenas inferir a desregulacao a partir de sensores, a
propria crianca sinaliza que precisa de um tempo — sem precisar explicar-se
e sem depender de conseguir verbalizar no momento.

A estrategia escolhida vem do kit de apoio preenchido pelo responsavel, e o
resultado registrado alimenta a sugestao das proximas vezes. E o mesmo
padrao dos aplicativos de regulacao emocional com validacao publicada:
sugerir a estrategia que ja funcionou para aquela crianca especifica.
"""

import datetime

from bson.objectid import ObjectId

from app import mongo

STATUS_ABERTO = 'aberto'
STATUS_ATENDIDO = 'atendido'
STATUS_ENCERRADO = 'encerrado'

RESULTADOS = ('ajudou', 'nao_ajudou', 'nao_informado')


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class BreakRequest:
    def criar(self, aluno_id, estrategia=None, origem='aluno'):
        """Registra um pedido de pausa.

        `estrategia` e opcional de proposito: em desregulacao, escolher ja
        pode ser demais. Avisar sem escolher precisa ser possivel.
        """
        aluno_oid = _to_object_id(aluno_id)
        if aluno_oid is None:
            raise ValueError('aluno_id invalido ao criar pedido de pausa')

        return mongo.db.break_requests.insert_one({
            'aluno_id': aluno_oid,
            'estrategia': estrategia,
            'origem': origem,
            'status': STATUS_ABERTO,
            'resultado': None,
            'criado_em': datetime.datetime.utcnow(),
            'atendido_em': None,
            'atendido_por': None,
            'encerrado_em': None,
        })

    def find_by_id(self, pedido_id):
        oid = _to_object_id(pedido_id)
        if oid is None:
            return None
        return mongo.db.break_requests.find_one({'_id': oid})

    def abertos_por_alunos(self, alunos_ids):
        """Pedidos em aberto de um conjunto de alunos (visao do professor)."""
        oids = [o for o in (_to_object_id(i) for i in alunos_ids) if o is not None]
        if not oids:
            return []
        return list(
            mongo.db.break_requests.find({
                'aluno_id': {'$in': oids},
                'status': {'$in': [STATUS_ABERTO, STATUS_ATENDIDO]},
            }).sort('criado_em', -1)
        )

    def historico_do_aluno(self, aluno_id, desde=None, limite=100):
        oid = _to_object_id(aluno_id)
        if oid is None:
            return []

        query = {'aluno_id': oid}
        if desde:
            query['criado_em'] = {'$gte': desde}

        return list(
            mongo.db.break_requests.find(query).sort('criado_em', -1).limit(limite)
        )

    def marcar_atendido(self, pedido_id, professor_id):
        oid = _to_object_id(pedido_id)
        if oid is None:
            return None
        return mongo.db.break_requests.update_one(
            {'_id': oid, 'status': STATUS_ABERTO},
            {'$set': {
                'status': STATUS_ATENDIDO,
                'atendido_em': datetime.datetime.utcnow(),
                'atendido_por': _to_object_id(professor_id),
            }},
        )

    def encerrar(self, pedido_id, resultado='nao_informado'):
        """Encerra o pedido e registra se a estrategia ajudou."""
        oid = _to_object_id(pedido_id)
        if oid is None:
            return None
        if resultado not in RESULTADOS:
            resultado = 'nao_informado'

        return mongo.db.break_requests.update_one(
            {'_id': oid},
            {'$set': {
                'status': STATUS_ENCERRADO,
                'resultado': resultado,
                'encerrado_em': datetime.datetime.utcnow(),
            }},
        )

    def eficacia_por_estrategia(self, aluno_id, dias=30):
        """Quantas vezes cada estrategia ajudou este aluno.

        Alimenta o "funcionou nas ultimas 3 vezes" da tela de pausa.
        """
        oid = _to_object_id(aluno_id)
        if oid is None:
            return {}

        desde = datetime.datetime.utcnow() - datetime.timedelta(days=dias)
        contagem = {}

        for pedido in mongo.db.break_requests.find({
            'aluno_id': oid,
            'criado_em': {'$gte': desde},
            'estrategia': {'$ne': None},
        }):
            estrategia = pedido['estrategia']
            registro = contagem.setdefault(estrategia, {'ajudou': 0, 'total': 0})
            registro['total'] += 1
            if pedido.get('resultado') == 'ajudou':
                registro['ajudou'] += 1

        return contagem

    @staticmethod
    def serializar(pedido):
        def iso(campo):
            valor = pedido.get(campo)
            return valor.isoformat() if valor else None

        return {
            '_id': str(pedido.get('_id')),
            'aluno_id': str(pedido.get('aluno_id')),
            'estrategia': pedido.get('estrategia'),
            'origem': pedido.get('origem', 'aluno'),
            'status': pedido.get('status', STATUS_ABERTO),
            'resultado': pedido.get('resultado'),
            'criado_em': iso('criado_em'),
            'atendido_em': iso('atendido_em'),
            'encerrado_em': iso('encerrado_em'),
        }
