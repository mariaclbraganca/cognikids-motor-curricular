"""
Forum de discussao entre professores e responsaveis.

O acesso ao Mongo usa o objeto compartilhado `mongo` (como os demais
models). A versao anterior lia current_app.extensions['pymongo'], que nao
devolve o PyMongo configurado por este projeto.
"""

import datetime
import logging

from bson.objectid import ObjectId

from app import mongo

logger = logging.getLogger(__name__)


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class ForumModel:
    def get_all_topics(self, apenas_ativos=True):
        """Todos os topicos, mais recentes primeiro."""
        query = {'is_active': True} if apenas_ativos else {}
        return list(mongo.db.forum_topics.find(query).sort('created_at', -1))

    def create_topic(self, topic_data):
        """Cria um topico.

        Recebe um dicionario (e nao argumentos posicionais), no mesmo padrao
        dos outros models.
        """
        autor_oid = _to_object_id(topic_data['author_id'])
        if autor_oid is None:
            raise ValueError('author_id invalido ao criar topico')

        return mongo.db.forum_topics.insert_one({
            'title': topic_data['title'],
            'content': topic_data['content'],
            'author_id': autor_oid,
            'author_name': topic_data.get('author_name', ''),
            'author_type': topic_data.get('author_type', ''),
            'category': topic_data.get('category'),
            'replies': [],
            'created_at': datetime.datetime.utcnow(),
            'updated_at': datetime.datetime.utcnow(),
            'is_active': True,
        })

    def get_topic_by_id(self, topic_id):
        oid = _to_object_id(topic_id)
        if oid is None:
            return None
        return mongo.db.forum_topics.find_one({'_id': oid})

    def add_reply(self, topic_id, reply_data):
        """Adiciona uma resposta a um topico."""
        topic_oid = _to_object_id(topic_id)
        autor_oid = _to_object_id(reply_data['author_id'])
        if topic_oid is None or autor_oid is None:
            return None

        reply = {
            'reply_id': ObjectId(),
            'content': reply_data['content'],
            'author_id': autor_oid,
            'author_name': reply_data.get('author_name', ''),
            'author_type': reply_data.get('author_type', ''),
            'created_at': datetime.datetime.utcnow(),
        }

        return mongo.db.forum_topics.update_one(
            {'_id': topic_oid},
            {'$push': {'replies': reply},
             '$set': {'updated_at': datetime.datetime.utcnow()}},
        )

    def update_topic(self, topic_id, updates):
        oid = _to_object_id(topic_id)
        if oid is None:
            return None

        protegidos = {'_id', 'author_id', 'replies', 'created_at'}
        dados = {k: v for k, v in (updates or {}).items() if k not in protegidos}
        if not dados:
            return None

        dados['updated_at'] = datetime.datetime.utcnow()
        return mongo.db.forum_topics.update_one({'_id': oid}, {'$set': dados})

    def delete_topic(self, topic_id):
        """Exclui um topico (soft delete)."""
        oid = _to_object_id(topic_id)
        if oid is None:
            return None
        return mongo.db.forum_topics.update_one(
            {'_id': oid},
            {'$set': {'is_active': False, 'updated_at': datetime.datetime.utcnow()}},
        )

    def get_topics_by_category(self, category):
        return list(mongo.db.forum_topics.find(
            {'category': category, 'is_active': True}
        ).sort('created_at', -1))

    def get_topics_by_author(self, author_id):
        oid = _to_object_id(author_id)
        if oid is None:
            return []
        return list(mongo.db.forum_topics.find(
            {'author_id': oid, 'is_active': True}
        ).sort('created_at', -1))

    @staticmethod
    def serializar(topico):
        """Converte um topico para o formato de resposta da API."""
        created_at = topico.get('created_at')
        updated_at = topico.get('updated_at')

        respostas = []
        for reply in topico.get('replies', []) or []:
            reply_created = reply.get('created_at')
            respostas.append({
                'reply_id': str(reply.get('reply_id', '')),
                'content': reply.get('content'),
                'author_id': str(reply.get('author_id')),
                'author_name': reply.get('author_name', ''),
                'author_type': reply.get('author_type', ''),
                'created_at': reply_created.isoformat() if reply_created else None,
            })

        return {
            '_id': str(topico.get('_id')),
            'title': topico.get('title'),
            'content': topico.get('content'),
            'author_id': str(topico.get('author_id')),
            'author_name': topico.get('author_name', ''),
            'author_type': topico.get('author_type', ''),
            'category': topico.get('category'),
            'replies': respostas,
            'reply_count': len(respostas),
            'created_at': created_at.isoformat() if created_at else None,
            'updated_at': updated_at.isoformat() if updated_at else None,
        }
