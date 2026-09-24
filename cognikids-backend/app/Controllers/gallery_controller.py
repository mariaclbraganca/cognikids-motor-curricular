# app/Controllers/gallery_controller.py
"""
Galeria de criacoes dos alunos.

O aluno envia um arquivo, o professor da turma aprova, e a turma inteira
(alunos, professor e responsaveis) enxerga o que foi aprovado.
"""

import logging
import os
import uuid

from flask import Blueprint, request, send_from_directory
from werkzeug.utils import secure_filename

from app.Models.class_model import Class
from app.Models.gallery_model import GalleryModel
from app.Utils.authz import pode_editar_turma, pode_ver_turma, to_object_id
from app.Utils.decorators import estudante_required, professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.abspath(os.getenv(
    'UPLOAD_FOLDER', os.path.join(os.getcwd(), 'uploads')
))
# Sempre absoluto: se UPLOAD_FOLDER vier relativo da variavel de ambiente,
# o Flask `send_from_directory` resolve caminho relativo contra
# `current_app.root_path` (a pasta de `app/`), nao contra o diretorio onde
# o arquivo foi de fato salvo (relativo ao cwd do processo) — os dois
# nunca coincidiam, e todo GET de arquivo da galeria retornava 404/500. Bug
# real, encontrado ao escrever o teste de controle de acesso deste endpoint.
EXTENSOES_PERMITIDAS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'txt', 'mp4'}

gallery_blueprint = Blueprint('gallery_bp', __name__)
gallery_model = GalleryModel()
class_model = Class()


def _extensao_permitida(filename):
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in EXTENSOES_PERMITIDAS
    )


def _serializar(criacao):
    created_at = criacao.get('created_at')
    return {
        '_id': str(criacao.get('_id')),
        'aluno_id': str(criacao.get('aluno_id')),
        'class_id': str(criacao.get('class_id')),
        'title': criacao.get('title'),
        'description': criacao.get('description', ''),
        'file_url': criacao.get('file_url'),
        'creation_type': criacao.get('creation_type', 'image'),
        'is_approved': criacao.get('is_approved', False),
        'created_at': created_at.isoformat() if created_at else None,
    }


@gallery_blueprint.route('/gallery/upload', methods=['POST'])
@token_required
@estudante_required
def upload_creation(current_user):
    """(ALUNO) Envia uma criacao para a galeria da sua turma."""
    try:
        if 'file' not in request.files:
            return dados_invalidos('O arquivo e obrigatorio')

        arquivo = request.files['file']
        class_id = request.form.get('class_id')
        title = request.form.get('title')

        if not class_id or not title:
            return dados_invalidos('class_id e title sao obrigatorios')

        if not arquivo.filename:
            return dados_invalidos('Nenhum arquivo selecionado')

        if not _extensao_permitida(arquivo.filename):
            return dados_invalidos(
                f'Extensao nao permitida. Aceitas: {", ".join(sorted(EXTENSOES_PERMITIDAS))}'
            )

        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Voce nao esta matriculado nesta turma')

        # secure_filename remove path traversal; o uuid evita que um upload
        # sobrescreva o arquivo de outro aluno com o mesmo nome.
        nome_seguro = secure_filename(arquivo.filename)
        nome_final = f"{uuid.uuid4().hex}_{nome_seguro}"

        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        arquivo.save(os.path.join(UPLOAD_FOLDER, nome_final))

        resultado = gallery_model.add_creation({
            'aluno_id': current_user['_id'],
            'class_id': turma['_id'],
            'title': title,
            'description': request.form.get('description', ''),
            'file_url': f'/api/gallery/files/{nome_final}',
            'creation_type': request.form.get('creation_type', 'image'),
        })

        return sucesso(
            message='Criacao enviada com sucesso! Aguardando aprovacao do professor.',
            status_code=201,
            creation_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao enviar criacao')


@gallery_blueprint.route('/gallery/files/<path:filename>', methods=['GET'])
@token_required
def get_file(current_user, filename):
    """Serve um arquivo da galeria — apenas a quem pode ver a turma dona da criacao.

    Antes servia qualquer arquivo a qualquer usuario autenticado, sem checar
    a turma (diferente dos demais endpoints da galeria, que ja checam
    `pode_ver_turma`) — uma criacao de uma crianca ficava acessivel a
    qualquer conta logada no sistema, bastando adivinhar/obter o nome do
    arquivo.
    """
    try:
        nome_seguro = secure_filename(filename)
        caminho = os.path.join(UPLOAD_FOLDER, nome_seguro)
        if not os.path.isfile(caminho):
            return nao_encontrado('Arquivo nao encontrado')

        criacao = gallery_model.get_creation_by_filename(nome_seguro)
        if not criacao:
            return nao_encontrado('Arquivo nao encontrado')

        turma = class_model.get_class_by_id(criacao['class_id'])
        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Acesso nao autorizado a este arquivo')

        return send_from_directory(UPLOAD_FOLDER, nome_seguro)

    except Exception as e:
        return erro_interno(e, 'ao servir arquivo da galeria')


@gallery_blueprint.route('/gallery/class/<string:class_id>', methods=['GET'])
@token_required
def get_class_gallery(current_user, class_id):
    """Criacoes aprovadas de uma turma."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Acesso nao autorizado a esta turma')

        criacoes = gallery_model.get_creations_by_class(class_id)
        return sucesso(data=[_serializar(c) for c in criacoes])

    except Exception as e:
        return erro_interno(e, 'ao listar galeria da turma')


@gallery_blueprint.route('/gallery/class/<string:class_id>/pending', methods=['GET'])
@token_required
@professor_required
def get_pending_creations(current_user, class_id):
    """(PROFESSOR) Criacoes aguardando aprovacao."""
    try:
        turma = class_model.get_class_by_id(class_id)
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        pendentes = gallery_model.get_pending_by_class(class_id)
        return sucesso(data=[_serializar(c) for c in pendentes])

    except Exception as e:
        return erro_interno(e, 'ao listar criacoes pendentes')


@gallery_blueprint.route('/gallery/my-creations', methods=['GET'])
@token_required
@estudante_required
def get_my_creations(current_user):
    """(ALUNO) Criacoes enviadas pelo proprio aluno, aprovadas ou nao."""
    try:
        criacoes = gallery_model.get_creations_by_student(str(current_user['_id']))
        return sucesso(data=[_serializar(c) for c in criacoes])

    except Exception as e:
        return erro_interno(e, 'ao listar minhas criacoes')


@gallery_blueprint.route('/gallery/creation/<string:creation_id>/approve', methods=['PUT'])
@token_required
@professor_required
def approve_creation(current_user, creation_id):
    """(PROFESSOR) Aprova uma criacao da sua turma."""
    try:
        criacao = gallery_model.get_creation_by_id(creation_id)
        if not criacao:
            return nao_encontrado('Criacao nao encontrada')

        turma = class_model.get_class_by_id(criacao['class_id'])
        if not pode_editar_turma(current_user, turma):
            return nao_autorizado('Acesso negado: nao e professor desta turma')

        resultado = gallery_model.approve_creation(creation_id, str(current_user['_id']))
        if resultado.modified_count == 0:
            return sucesso(message='Criacao ja estava aprovada')

        return sucesso(message='Criacao aprovada com sucesso!')

    except Exception as e:
        return erro_interno(e, 'ao aprovar criacao')


@gallery_blueprint.route('/gallery/creation/<string:creation_id>', methods=['DELETE'])
@token_required
def delete_creation(current_user, creation_id):
    """Remove uma criacao (o proprio aluno ou o professor da turma)."""
    try:
        criacao = gallery_model.get_creation_by_id(creation_id)
        if not criacao:
            return nao_encontrado('Criacao nao encontrada')

        eh_autor = str(criacao.get('aluno_id')) == str(current_user['_id'])
        turma = class_model.get_class_by_id(criacao['class_id'])
        eh_professor_da_turma = pode_editar_turma(current_user, turma)

        if not (eh_autor or eh_professor_da_turma):
            return nao_autorizado('Acesso nao autorizado a esta criacao')

        gallery_model.delete_creation(creation_id)
        return sucesso(message='Criacao removida com sucesso')

    except Exception as e:
        return erro_interno(e, 'ao remover criacao')
