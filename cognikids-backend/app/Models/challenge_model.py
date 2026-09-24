# app/Models/challenge_model.py
from app import mongo
from bson.objectid import ObjectId
import datetime


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class ChallengeModel:
    def create_challenge(self, challenge_data):
        """Cria um novo desafio."""
        return mongo.db.challenges.insert_one({
            "title": challenge_data['title'],
            "description": challenge_data['description'],
            "points": challenge_data.get('points', 10),
            # class_id e persistido: e ele que define quem pode gerir o desafio
            "class_id": _to_object_id(challenge_data.get('class_id')),
            "start_date": datetime.datetime.utcnow(),
            "end_date": challenge_data.get('end_date') or challenge_data.get('dueDate'),
            "is_active": True,
            "created_by": _to_object_id(challenge_data['created_by'])
        })

    def get_active_challenges(self, class_ids=None):
        """Busca os desafios ativos, opcionalmente restritos a turmas.

        Desafios sem turma (class_id nulo) sao globais e aparecem para todos.
        """
        query = {"is_active": True}

        if class_ids is not None:
            oids = [o for o in (_to_object_id(c) for c in class_ids) if o is not None]
            query["$or"] = [
                {"class_id": {"$in": oids}},
                {"class_id": None},
                {"class_id": {"$exists": False}},
            ]

        return list(mongo.db.challenges.find(query).sort("start_date", -1))

    def complete_challenge(self, aluno_id, challenge_id):
        """Regista que um aluno completou um desafio."""
        aluno_oid = _to_object_id(aluno_id)
        challenge_oid = _to_object_id(challenge_id)
        if aluno_oid is None or challenge_oid is None:
            return None

        # Evita duplicados
        if mongo.db.challenge_completions.find_one({
            "aluno_id": aluno_oid,
            "challenge_id": challenge_oid
        }):
            return None

        return mongo.db.challenge_completions.insert_one({
            "aluno_id": aluno_oid,
            "challenge_id": challenge_oid,
            "completed_at": datetime.datetime.utcnow()
        })

    def get_student_completions(self, aluno_id):
        """Busca todos os desafios que um aluno já completou."""
        aluno_oid = _to_object_id(aluno_id)
        if aluno_oid is None:
            return []
        return list(mongo.db.challenge_completions.find({"aluno_id": aluno_oid}))

    def get_challenge_by_id(self, challenge_id):
        """Busca um desafio específico pelo seu ID."""
        challenge_oid = _to_object_id(challenge_id)
        if challenge_oid is None:
            return None
        return mongo.db.challenges.find_one({"_id": challenge_oid})

    def update_challenge(self, challenge_id, update_data):
        """Atualiza um desafio existente."""
        challenge_oid = _to_object_id(challenge_id)
        if challenge_oid is None:
            return None

        protegidos = {'_id', 'created_by', 'class_id', 'start_date'}
        dados = {k: v for k, v in (update_data or {}).items() if k not in protegidos}
        if not dados:
            return None

        return mongo.db.challenges.update_one(
            {"_id": challenge_oid}, {"$set": dados}
        )

    def delete_challenge(self, challenge_id):
        """Remove um desafio e as suas conclusoes."""
        challenge_oid = _to_object_id(challenge_id)
        if challenge_oid is None:
            return None
        mongo.db.challenge_completions.delete_many({"challenge_id": challenge_oid})
        return mongo.db.challenges.delete_one({"_id": challenge_oid})