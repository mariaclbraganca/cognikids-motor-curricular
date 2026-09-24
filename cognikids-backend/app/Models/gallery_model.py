# app/Models/gallery_model.py
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


class GalleryModel:
    def add_creation(self, creation_data):
        """Adiciona uma nova criação de um aluno à galeria."""
        return mongo.db.gallery_creations.insert_one({
            "aluno_id": _to_object_id(creation_data['aluno_id']),
            "class_id": _to_object_id(creation_data['class_id']),
            "title": creation_data['title'],
            "description": creation_data.get('description', ''),
            "file_url": creation_data['file_url'],  # URL para o ficheiro (upload será tratado no controller)
            "creation_type": creation_data.get('creation_type', 'image'), # pode ser 'image', 'text', 'video'
            "created_at": datetime.datetime.utcnow(),
            "is_approved": False  # Pode ser útil ter um sistema de aprovação por parte dos professores
        })

    def get_creations_by_student(self, aluno_id):
        """Busca todas as criações de um aluno específico."""
        oid = _to_object_id(aluno_id)
        if oid is None:
            return []
        return list(mongo.db.gallery_creations.find({
            "aluno_id": oid
        }).sort("created_at", -1))

    def get_creations_by_class(self, class_id):
        """Busca todas as criações aprovadas de uma turma."""
        oid = _to_object_id(class_id)
        if oid is None:
            return []
        return list(mongo.db.gallery_creations.find({
            "class_id": oid,
            "is_approved": True
        }).sort("created_at", -1))

    def get_pending_by_class(self, class_id):
        """Busca as criações de uma turma aguardando aprovação."""
        oid = _to_object_id(class_id)
        if oid is None:
            return []
        return list(mongo.db.gallery_creations.find({
            "class_id": oid,
            "is_approved": False
        }).sort("created_at", -1))

    def get_creation_by_id(self, creation_id):
        """Busca uma criação pelo seu ID."""
        oid = _to_object_id(creation_id)
        if oid is None:
            return None
        return mongo.db.gallery_creations.find_one({"_id": oid})

    def get_creation_by_filename(self, filename):
        """Busca a criação dona de um arquivo, pelo nome salvo em disco.

        file_url é sempre gravado como '/api/gallery/files/{nome_final}'
        (ver gallery_controller.upload_creation) — reconstruo a mesma string
        exata em vez de usar regex, evitando qualquer risco de o nome do
        arquivo (entrada de usuário, ainda que já filtrada por
        secure_filename) ser interpretado como padrão de regex.
        """
        return mongo.db.gallery_creations.find_one({
            "file_url": f"/api/gallery/files/{filename}"
        })

    def approve_creation(self, creation_id, professor_id):
        """Permite que um professor aprove uma criação para ser exibida."""
        oid = _to_object_id(creation_id)
        if oid is None:
            return None
        return mongo.db.gallery_creations.update_one(
            {"_id": oid, "is_approved": False},
            {
                "$set": {
                    "is_approved": True,
                    "approved_by": _to_object_id(professor_id),
                    "approved_at": datetime.datetime.utcnow()
                }
            }
        )

    def delete_creation(self, creation_id):
        """Remove uma criação."""
        oid = _to_object_id(creation_id)
        if oid is None:
            return None
        return mongo.db.gallery_creations.delete_one({"_id": oid})