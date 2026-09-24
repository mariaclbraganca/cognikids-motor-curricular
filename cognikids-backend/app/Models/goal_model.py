from app import mongo
from bson.objectid import ObjectId
from datetime import datetime


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class Goal:
    @property
    def collection(self):
        """Resolve a colecao a cada uso.

        Capturar mongo.db no __init__ prendia a instancia ao contexto de
        aplicacao vigente no momento do import, o que quebra com o padrao
        factory (e nos testes, onde a app e recriada a cada caso).
        """
        return mongo.db.goals

    @staticmethod
    def serializar(meta):
        """Converte uma meta para o formato de resposta da API.

        Todo ObjectId vira string: 'created_by' escapava da serializacao
        manual dos controllers e quebrava o jsonify.
        """
        return {
            '_id': str(meta.get('_id')),
            'student_id': str(meta.get('student_id')),
            'title': meta.get('title'),
            'description': meta.get('description'),
            'deadline': meta.get('deadline'),
            'progress': meta.get('progress', 0),
            'status': meta.get('status', 'current'),
            'created_by': str(meta['created_by']) if meta.get('created_by') else None,
            'created_at': meta['created_at'].isoformat() if meta.get('created_at') else None,
            'updated_at': meta['updated_at'].isoformat() if meta.get('updated_at') else None,
        }

    def create_goal(self, goal_data):
        """Cria uma nova meta para um aluno."""
        dados = dict(goal_data)
        dados['created_at'] = datetime.utcnow()
        dados['updated_at'] = datetime.utcnow()
        dados['progress'] = dados.get('progress', 0)
        dados['status'] = dados.get('status', 'current')
        dados['student_id'] = _to_object_id(dados.get('student_id'))

        if dados.get('created_by'):
            dados['created_by'] = _to_object_id(dados['created_by'])

        return self.collection.insert_one(dados)

    def find_by_student_id(self, student_id):
        """Encontra todas as metas de um aluno específico."""
        oid = _to_object_id(student_id)
        if oid is None:
            return []
        return list(self.collection.find({'student_id': oid}).sort('created_at', -1))

    def find_by_id(self, goal_id):
        """Encontra uma meta pelo seu ID."""
        oid = _to_object_id(goal_id)
        if oid is None:
            return None
        return self.collection.find_one({'_id': oid})

    def update_goal(self, goal_id, update_data):
        """Atualiza uma meta."""
        oid = _to_object_id(goal_id)
        if oid is None:
            return None

        protegidos = {'_id', 'student_id', 'created_by', 'created_at'}
        dados = {k: v for k, v in (update_data or {}).items() if k not in protegidos}
        if not dados:
            return None

        dados['updated_at'] = datetime.utcnow()
        return self.collection.update_one({'_id': oid}, {'$set': dados})

    def delete_goal(self, goal_id):
        """Deleta uma meta."""
        oid = _to_object_id(goal_id)
        if oid is None:
            return None
        return self.collection.delete_one({'_id': oid})
