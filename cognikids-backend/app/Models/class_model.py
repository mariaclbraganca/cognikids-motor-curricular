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


class Class:
    """Turmas do CogniKids.

    A colecao canonica e 'turmas'. Partes antigas do codigo gravavam em
    'classes', o que fazia as checagens de autorizacao nao encontrarem a
    turma e, por consequencia, liberarem o acesso.
    """

    def create_class(self, class_data):
        """
        Cria uma nova turma na base de dados
        """
        return mongo.db.turmas.insert_one({
            "name": class_data.get('name') or class_data.get('nome', 'Sem Nome'),
            "grade": class_data.get('grade', ''),        # Ex: "3º Ano", "1ª Série"
            "section": class_data.get('section', ''),    # Ex: "A", "B", "C"
            "teacher_id": _to_object_id(class_data['teacher_id']),
            "school_year": class_data.get('school_year', ''),  # Ex: "2024"
            "alunos_ids": [],                       # Lista de IDs de alunos
            "subjects": class_data.get('subjects', []), # Lista de matérias
            "created_at": datetime.datetime.utcnow(),
            "is_active": True,
            "schedule": {}                          # Horário das aulas
        })

    def enroll_student(self, class_id, student_id):
        """
        Matricula um aluno em uma turma
        """
        class_oid = _to_object_id(class_id)
        student_oid = _to_object_id(student_id)
        if class_oid is None or student_oid is None:
            return None
        return mongo.db.turmas.update_one(
            {"_id": class_oid},
            {"$addToSet": {"alunos_ids": student_oid}}
        )

    def remove_student(self, class_id, student_id):
        """
        Remove um aluno de uma turma (dos dois campos historicos)
        """
        class_oid = _to_object_id(class_id)
        student_oid = _to_object_id(student_id)
        if class_oid is None or student_oid is None:
            return None
        return mongo.db.turmas.update_one(
            {"_id": class_oid},
            {"$pull": {"alunos_ids": student_oid, "students": student_oid}}
        )

    def get_class_by_id(self, class_id):
        """
        Busca uma turma específica pelo seu ID
        """
        class_oid = _to_object_id(class_id)
        if class_oid is None:
            return None
        return mongo.db.turmas.find_one({"_id": class_oid})

    def add_student_to_class(self, class_id, student_id):
        """
        Adiciona um aluno a uma turma
        """
        return self.enroll_student(class_id, student_id)

    def get_teacher_classes(self, teacher_id):
        """
        Busca todas as turmas ativas de um professor
        """
        teacher_id_obj = _to_object_id(teacher_id)
        if teacher_id_obj is None:
            return []

        classes = list(mongo.db.turmas.find(
            {"teacher_id": teacher_id_obj}
        ).sort("created_at", -1))

        # Filtra apenas turmas ativas (aceita os dois nomes historicos do campo)
        return [
            c for c in classes
            if c.get('ativa', True) and c.get('is_active', True)
        ]

    # Alias usado pelo schedule_controller
    get_classes_by_teacher = get_teacher_classes

    def get_student_classes(self, student_id):
        """
        Busca todas as turmas de um aluno.

        Considera tanto a matricula na turma (alunos_ids/students) quanto o
        vinculo reverso gravado em users.turma_id.
        """
        student_oid = _to_object_id(student_id)
        if student_oid is None:
            return []

        criterios = [
            {"alunos_ids": student_oid},
            {"students": student_oid},
        ]

        aluno = mongo.db.users.find_one({"_id": student_oid}, {"turma_id": 1})
        if aluno and aluno.get('turma_id'):
            criterios.append({"_id": aluno['turma_id']})

        return list(mongo.db.turmas.find({"$or": criterios}).sort("created_at", -1))

    def get_parent_classes(self, filhos_ids):
        """
        Busca as turmas dos filhos de um responsavel.
        """
        turmas = {}
        for filho_id in filhos_ids or []:
            for turma in self.get_student_classes(filho_id):
                turmas[turma['_id']] = turma
        return list(turmas.values())

    def get_all_classes(self):
        """
        Busca todas as turmas ativas
        """
        return list(mongo.db.turmas.find().sort("created_at", -1))

    def update_class(self, class_id, update_data):
        """
        Atualiza informações de uma turma.

        Campos estruturais (_id, teacher_id, alunos_ids) nao podem ser
        alterados por aqui: a troca de titular e a matricula tem fluxos
        proprios com suas checagens de autorizacao.
        """
        class_oid = _to_object_id(class_id)
        if class_oid is None:
            return None

        protegidos = {'_id', 'teacher_id', 'alunos_ids', 'students', 'created_at'}
        dados = {k: v for k, v in (update_data or {}).items() if k not in protegidos}
        if not dados:
            return None

        return mongo.db.turmas.update_one({"_id": class_oid}, {"$set": dados})

    def deactivate_class(self, class_id):
        """
        Desativa uma turma (soft delete)
        """
        class_oid = _to_object_id(class_id)
        if class_oid is None:
            return None
        return mongo.db.turmas.update_one(
            {"_id": class_oid},
            {"$set": {"is_active": False}}
        )

    def get_class_students(self, class_id):
        """
        Busca os IDs de todos os alunos de uma turma específica
        """
        class_oid = _to_object_id(class_id)
        if class_oid is None:
            return []

        class_data = mongo.db.turmas.find_one(
            {"_id": class_oid},
            {"alunos_ids": 1, "students": 1}
        )
        if not class_data:
            return []

        ids = {
            oid for oid in (
                _to_object_id(a)
                for a in (class_data.get('alunos_ids', []) or [])
                + (class_data.get('students', []) or [])
            )
            if oid is not None
        }

        # Inclui alunos vinculados pelo campo reverso users.turma_id
        for aluno in mongo.db.users.find({"turma_id": class_oid}, {"_id": 1}):
            ids.add(aluno['_id'])

        return list(ids)
