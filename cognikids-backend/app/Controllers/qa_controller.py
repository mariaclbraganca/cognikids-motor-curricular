# app/Controllers/qa_controller.py
"""
Perguntas e respostas entre aluno e professor.

Aluno pergunta na turma em que esta matriculado; o professor titular
responde; o responsavel acompanha as perguntas dos filhos.
"""

import logging

from flask import Blueprint, request

from app.Models.class_model import Class
from app.Models.qa_model import QAModel
from app.Models.user_model import User
from app.Utils.authz import pode_ver_aluno, pode_ver_turma, to_object_id
from app.Utils.decorators import estudante_required, professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

qa_blueprint = Blueprint('qa_bp', __name__)
qa_model = QAModel()
class_model = Class()
user_model = User()


def _serializar(pergunta):
    asked = pergunta.get('asked_at')
    answered = pergunta.get('answered_at')
    return {
        '_id': str(pergunta.get('_id')),
        'aluno_id': str(pergunta.get('aluno_id')),
        'class_id': str(pergunta.get('class_id')),
        'professor_id': str(pergunta.get('professor_id')),
        'question_text': pergunta.get('question_text'),
        'answer_text': pergunta.get('answer_text'),
        'status': pergunta.get('status', 'asked'),
        'asked_at': asked.isoformat() if asked else None,
        'answered_at': answered.isoformat() if answered else None,
    }


@qa_blueprint.route('/qa/ask', methods=['POST'])
@token_required
@estudante_required
def ask_question(current_user):
    """(ALUNO) Envia uma pergunta ao professor da turma."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('class_id') or not data.get('question_text'):
            return dados_invalidos('class_id e question_text sao obrigatorios')

        turma = class_model.get_class_by_id(data['class_id'])
        if not turma:
            return nao_encontrado('Turma nao encontrada')

        # pode_ver_turma cobre matricula por alunos_ids, students e turma_id
        if not pode_ver_turma(current_user, turma):
            return nao_autorizado('Voce nao esta matriculado nesta turma')

        if not turma.get('teacher_id'):
            return dados_invalidos('Esta turma nao possui professor associado')

        resultado = qa_model.ask_question({
            'aluno_id': current_user['_id'],
            'class_id': turma['_id'],
            'professor_id': turma['teacher_id'],
            'question_text': data['question_text'],
        })

        return sucesso(
            message='Pergunta enviada com sucesso!',
            status_code=201,
            question_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao enviar pergunta')


@qa_blueprint.route('/qa/questions/professor', methods=['GET'])
@token_required
@professor_required
def get_questions_for_professor(current_user):
    """(PROFESSOR) Perguntas direcionadas ao professor logado."""
    try:
        perguntas = qa_model.get_questions_for_professor(str(current_user['_id']))
        return sucesso(data=[_serializar(p) for p in perguntas])

    except Exception as e:
        return erro_interno(e, 'ao listar perguntas do professor')


@qa_blueprint.route('/qa/questions/student/<string:student_id>', methods=['GET'])
@token_required
def get_student_questions(current_user, student_id):
    """Perguntas de um aluno (proprio, responsavel ou professor da turma)."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado(
                'Acesso nao autorizado para ver as perguntas deste aluno'
            )

        perguntas = qa_model.get_questions_from_student(
            str(aluno_oid), request.args.get('class_id')
        )
        return sucesso(data=[_serializar(p) for p in perguntas])

    except Exception as e:
        return erro_interno(e, 'ao listar perguntas do aluno')


@qa_blueprint.route('/qa/answer/<string:question_id>', methods=['PUT'])
@token_required
@professor_required
def answer_question(current_user, question_id):
    """(PROFESSOR) Responde a uma pergunta direcionada a si."""
    try:
        data = request.get_json(silent=True) or {}

        if not data.get('answer_text'):
            return dados_invalidos('O texto da resposta e obrigatorio')

        pergunta = qa_model.get_question_by_id(question_id)
        if not pergunta:
            return nao_encontrado('Pergunta nao encontrada')

        if str(pergunta.get('professor_id')) != str(current_user['_id']):
            return nao_autorizado('Esta pergunta nao foi direcionada a voce')

        qa_model.answer_question(
            question_id, data['answer_text'], str(current_user['_id'])
        )

        return sucesso(message='Pergunta respondida com sucesso!')

    except Exception as e:
        return erro_interno(e, 'ao responder pergunta')
