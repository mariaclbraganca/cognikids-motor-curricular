"""
Vinculo responsavel-crianca, pendente de confirmacao por um terceiro.

Antes, POST /api/parents/link-child associava um responsavel a uma crianca
so pelo e-mail dela, sem nenhuma confirmacao — bastava ao atacante se
autorregistrar como 'pai' (rota publica, ver Utils/roles.py) e saber o
e-mail de qualquer aluno para ganhar acesso a biometria, alertas e perfil
funcional dela (ADR-010). Agora o vinculo nasce pendente, em
'vinculos_pendentes', e so passa a valer — Users.filhos_ids populado — quando
um professor de uma turma do aluno confirma.
"""

import datetime

from bson.objectid import ObjectId

from app import mongo

PENDENTE = 'pendente'
CONFIRMADO = 'confirmado'
RECUSADO = 'recusado'


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class Vinculo:
    def criar_pendente(self, responsavel_id, aluno_id):
        """Cria um pedido de vinculo pendente, ou devolve o existente.

        Idempotente: pedir de novo enquanto o pedido anterior ainda esta
        pendente ou ja foi confirmado nao cria duplicata. Um pedido recusado
        nao bloqueia uma nova tentativa — a escola pode ter errado, ou o
        vinculo pode ter passado a ser legitimo depois.
        """
        responsavel_oid = _to_object_id(responsavel_id)
        aluno_oid = _to_object_id(aluno_id)
        if responsavel_oid is None or aluno_oid is None:
            raise ValueError('IDs invalidos ao criar vinculo pendente')

        existente = mongo.db.vinculos_pendentes.find_one({
            'responsavel_id': responsavel_oid,
            'aluno_id': aluno_oid,
            'status': {'$in': [PENDENTE, CONFIRMADO]},
        })
        if existente:
            return existente

        documento = {
            'responsavel_id': responsavel_oid,
            'aluno_id': aluno_oid,
            'status': PENDENTE,
            'criado_em': datetime.datetime.utcnow(),
            'confirmado_por': None,
            'confirmado_em': None,
        }
        resultado = mongo.db.vinculos_pendentes.insert_one(documento)
        documento['_id'] = resultado.inserted_id
        return documento

    def obter(self, vinculo_id):
        oid = _to_object_id(vinculo_id)
        if oid is None:
            return None
        return mongo.db.vinculos_pendentes.find_one({'_id': oid})

    def pendentes_para_alunos(self, alunos_ids):
        """Pedidos ainda pendentes para um conjunto de alunos — fila do professor."""
        oids = [o for o in (_to_object_id(i) for i in (alunos_ids or [])) if o is not None]
        if not oids:
            return []
        return list(
            mongo.db.vinculos_pendentes.find({
                'aluno_id': {'$in': oids},
                'status': PENDENTE,
            }).sort([('criado_em', 1), ('_id', 1)])
        )

    def pedidos_do_responsavel(self, responsavel_id):
        """Todos os pedidos do responsavel, qualquer status — visibilidade dele."""
        oid = _to_object_id(responsavel_id)
        if oid is None:
            return []
        return list(
            mongo.db.vinculos_pendentes.find({'responsavel_id': oid})
            .sort([('criado_em', -1), ('_id', -1)])
        )

    def decidir(self, vinculo_id, professor_id, aprovar):
        """Confirma ou recusa um pedido pendente.

        Idempotente por desenho, mesmo padrao de
        curriculum_service.aprovar_adaptacao no satelite: o filtro exige
        status ainda PENDENTE, entao decidir duas vezes nao sobrescreve a
        primeira decisao — o chamador le matched_count para saber se algo
        mudou.
        """
        oid = _to_object_id(vinculo_id)
        professor_oid = _to_object_id(professor_id)
        if oid is None or professor_oid is None:
            return None

        novo_status = CONFIRMADO if aprovar else RECUSADO
        return mongo.db.vinculos_pendentes.update_one(
            {'_id': oid, 'status': PENDENTE},
            {'$set': {
                'status': novo_status,
                'confirmado_por': professor_oid,
                'confirmado_em': datetime.datetime.utcnow(),
            }},
        )

    @staticmethod
    def serializar(vinculo):
        criado_em = vinculo.get('criado_em')
        confirmado_em = vinculo.get('confirmado_em')
        return {
            '_id': str(vinculo.get('_id')),
            'responsavel_id': str(vinculo.get('responsavel_id')),
            'aluno_id': str(vinculo.get('aluno_id')),
            'status': vinculo.get('status'),
            'criado_em': criado_em.isoformat() if criado_em else None,
            'confirmado_por': str(vinculo['confirmado_por']) if vinculo.get('confirmado_por') else None,
            'confirmado_em': confirmado_em.isoformat() if confirmado_em else None,
        }
