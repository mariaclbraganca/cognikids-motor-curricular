import logging

from bson.objectid import ObjectId
from pymongo.errors import PyMongoError, ConnectionFailure, ServerSelectionTimeoutError

from app import mongo
from app.Utils.roles import normalizar_tipo, variacoes_de, ESTUDANTE, RESPONSAVEL, PROFESSOR

logger = logging.getLogger(__name__)

# Campos nunca devolvidos ao cliente
PROJECAO_PUBLICA = {'senha': 0, 'password': 0}

# Campos que nao podem ser alterados por update_user
CAMPOS_PROTEGIDOS = {'_id', 'senha', 'password', 'tipo'}


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class User:
    def create_user(self, user_data):
        """Cria um novo utilizador.

        O campo 'senha' ja deve chegar com o hash gerado pelo controller.
        Retorna sempre {'success': bool, 'message': str, 'user_id': str|None}.
        """
        try:
            tipo = normalizar_tipo(user_data.get('tipo'))
            if not tipo:
                return {'success': False, 'message': 'Tipo de usuario invalido', 'user_id': None}

            new_user = {
                'nome': user_data['nome'],
                'email': user_data['email'],
                'senha': user_data['senha'],
                'tipo': tipo,
            }

            if tipo == RESPONSAVEL:
                new_user['filhos_ids'] = []

            if tipo == PROFESSOR:
                new_user['turmas_ids'] = []

            if tipo == ESTUDANTE:
                turma_id = _to_object_id(user_data.get('turma_id'))
                new_user['turma_id'] = turma_id

            result = mongo.db.users.insert_one(new_user)
            logger.info('Usuario criado: %s (%s)', result.inserted_id, tipo)

            return {
                'success': True,
                'message': 'Usuario criado com sucesso',
                'user_id': str(result.inserted_id),
            }

        except (ServerSelectionTimeoutError, ConnectionFailure) as e:
            logger.error('Falha de conexao com MongoDB ao criar usuario: %s', e)
            return {'success': False, 'message': 'Falha na conexao com o banco de dados', 'user_id': None}

        except PyMongoError as e:
            logger.error('Erro do MongoDB ao criar usuario: %s', e)
            return {'success': False, 'message': 'Erro de persistencia no banco de dados', 'user_id': None}

    def find_user_by_email(self, email):
        """Encontra um utilizador pelo email (documento completo, com hash)."""
        try:
            return mongo.db.users.find_one({'email': email})
        except PyMongoError as e:
            logger.error('Erro na busca por email: %s', e)
            return None

    # Alias historico usado pelo student_controller
    find_by_email = find_user_by_email

    def find_user_by_id(self, user_id):
        """Encontra um utilizador pelo ID."""
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        try:
            return mongo.db.users.find_one({'_id': oid})
        except PyMongoError as e:
            logger.error('Erro na busca por ID: %s', e)
            return None

    def find_public_by_id(self, user_id):
        """Como find_user_by_id, mas sem os campos sensiveis."""
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        try:
            return mongo.db.users.find_one({'_id': oid}, PROJECAO_PUBLICA)
        except PyMongoError as e:
            logger.error('Erro na busca publica por ID: %s', e)
            return None

    def update_user(self, user_id, update_data):
        """Atualiza os dados de um utilizador.

        Ignora silenciosamente campos protegidos (_id, senha, tipo): a troca
        de senha e a mudanca de perfil tem fluxos proprios.
        """
        oid = _to_object_id(user_id)
        if oid is None:
            return None

        dados = {k: v for k, v in (update_data or {}).items() if k not in CAMPOS_PROTEGIDOS}

        # turma_id precisa ser ObjectId para casar com as queries de turma
        if 'turma_id' in dados and dados['turma_id'] is not None:
            dados['turma_id'] = _to_object_id(dados['turma_id'])

        if not dados:
            return None

        return mongo.db.users.update_one({'_id': oid}, {'$set': dados})

    def update_password(self, user_id, hashed_password):
        """Atualiza a senha (hash gerado pelo controller)."""
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        return mongo.db.users.update_one(
            {'_id': oid}, {'$set': {'senha': hashed_password}}
        )

    def delete_user(self, user_id):
        """Remove um utilizador."""
        oid = _to_object_id(user_id)
        if oid is None:
            return None
        return mongo.db.users.delete_one({'_id': oid})

    def find_students_by_ids(self, ids):
        """Busca alunos por uma lista de IDs, sem campos sensiveis."""
        oids = [o for o in (_to_object_id(i) for i in ids) if o is not None]
        if not oids:
            return []
        return list(mongo.db.users.find({'_id': {'$in': oids}}, PROJECAO_PUBLICA))

    def find_students_by_class_ids(self, turmas_ids):
        """Busca alunos vinculados a qualquer uma das turmas informadas."""
        oids = [o for o in (_to_object_id(i) for i in turmas_ids) if o is not None]
        if not oids:
            return []
        return list(mongo.db.users.find(
            {
                'tipo': {'$in': variacoes_de(ESTUDANTE)},
                'turma_id': {'$in': oids},
            },
            PROJECAO_PUBLICA,
        ))

    def link_child_to_parent(self, parent_id, child_id):
        """Adiciona um filho a lista de filhos de um responsavel."""
        parent_oid = _to_object_id(parent_id)
        child_oid = _to_object_id(child_id)
        if parent_oid is None or child_oid is None:
            return None
        return mongo.db.users.update_one(
            {'_id': parent_oid}, {'$addToSet': {'filhos_ids': child_oid}}
        )

    def unlink_child_from_parent(self, parent_id, child_id):
        """Remove o vinculo entre responsavel e filho."""
        parent_oid = _to_object_id(parent_id)
        child_oid = _to_object_id(child_id)
        if parent_oid is None or child_oid is None:
            return None
        return mongo.db.users.update_one(
            {'_id': parent_oid}, {'$pull': {'filhos_ids': child_oid}}
        )

    def add_class_to_teacher(self, teacher_id, class_id):
        """Vincula uma turma ao professor (lista desnormalizada)."""
        teacher_oid = _to_object_id(teacher_id)
        class_oid = _to_object_id(class_id)
        if teacher_oid is None or class_oid is None:
            return None
        return mongo.db.users.update_one(
            {'_id': teacher_oid}, {'$addToSet': {'turmas_ids': class_oid}}
        )

    def remove_class_from_teacher(self, teacher_id, class_id):
        teacher_oid = _to_object_id(teacher_id)
        class_oid = _to_object_id(class_id)
        if teacher_oid is None or class_oid is None:
            return None
        return mongo.db.users.update_one(
            {'_id': teacher_oid}, {'$pull': {'turmas_ids': class_oid}}
        )
