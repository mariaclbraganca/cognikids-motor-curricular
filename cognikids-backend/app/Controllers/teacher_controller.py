"""
Endpoints do perfil Professor.

Toda rota que recebe um student_id valida o vinculo professor-aluno via
app.Utils.authz. Sem isso, qualquer professor autenticado conseguia ler o
historico biometrico de alunos de outras turmas.
"""

import datetime
import logging

from bson.objectid import ObjectId
from flask import Blueprint, request

from app import mongo
from app.Models.alert_model import Alert
from app.Models.class_model import Class
from app.Models.feeling_model import Feeling
from app.Models.grade_model import Grade
from app.Models.user_model import User
from app.Models.vinculo_model import Vinculo
from app.Utils.authz import (
    alunos_do_professor,
    alunos_visiveis,
    pode_editar_aluno,
    pode_ver_aluno,
    to_object_id,
    turmas_do_professor,
)
from app.Utils.decorators import professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

teacher_blueprint = Blueprint('teacher', __name__)

feeling_model = Feeling()
user_model = User()
class_model = Class()
alert_model = Alert()
grade_model = Grade()
vinculo_model = Vinculo()


def _serializar_aluno(aluno):
    """Formata um aluno para resposta, sem campos sensiveis."""
    aluno.pop('senha', None)
    aluno.pop('password', None)
    aluno['_id'] = str(aluno['_id'])
    if aluno.get('turma_id'):
        aluno['turma_id'] = str(aluno['turma_id'])
    return aluno


@teacher_blueprint.route('/feelings/all', methods=['GET'])
@token_required
@professor_required
def get_all_feelings(current_user):
    """Sentimentos registrados pelos alunos das turmas do professor."""
    try:
        alunos_ids = alunos_visiveis(current_user)
        if not alunos_ids:
            return sucesso(data=[])

        feelings = feeling_model.find_feelings_by_aluno_ids([str(a) for a in alunos_ids])
        for feeling in feelings:
            feeling['_id'] = str(feeling['_id'])
            feeling['aluno_id'] = str(feeling['aluno_id'])
            if feeling.get('timestamp'):
                feeling['timestamp'] = feeling['timestamp'].isoformat()

        return sucesso(data=feelings)

    except Exception as e:
        return erro_interno(e, 'ao buscar sentimentos')


@teacher_blueprint.route('/students/<string:student_id>/feelings', methods=['GET'])
@token_required
def get_student_feelings(current_user, student_id):
    """Sentimentos de um aluno. Acessivel ao professor da turma e ao responsavel."""
    try:
        aluno_oid = to_object_id(student_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado(
                'Acesso nao autorizado para ver os sentimentos deste aluno'
            )

        feelings = feeling_model.find_feelings_by_aluno_id(str(aluno_oid))
        for feeling in feelings:
            feeling['_id'] = str(feeling['_id'])
            feeling['aluno_id'] = str(feeling['aluno_id'])
            if feeling.get('timestamp'):
                feeling['timestamp'] = feeling['timestamp'].isoformat()

        if not feelings:
            return sucesso(data=[], message='Nenhum sentimento registado para este aluno')

        return sucesso(data=feelings)

    except Exception as e:
        return erro_interno(e, 'ao buscar sentimentos do aluno')


@teacher_blueprint.route('/<string:teacher_id>/students', methods=['GET'])
@token_required
@professor_required
def get_teacher_students(current_user, teacher_id):
    """Alunos das turmas de um professor (apenas o proprio)."""
    try:
        if str(current_user.get('_id')) != teacher_id:
            return nao_autorizado(
                'Acesso nao autorizado: voce so pode ver seus proprios alunos'
            )

        return _listar_alunos(current_user)

    except Exception as e:
        return erro_interno(e, 'ao buscar alunos do professor')


@teacher_blueprint.route('/all_students', methods=['GET'])
@token_required
@professor_required
def get_all_students_teacher(current_user):
    """Todos os alunos de todas as turmas do professor logado."""
    try:
        return _listar_alunos(current_user)
    except Exception as e:
        return erro_interno(e, 'ao buscar todos os alunos')


def _listar_alunos(current_user):
    # alunos_visiveis aplica o consentimento: aluno cujo responsavel nao
    # autorizou o compartilhamento com a escola nao aparece para o professor.
    alunos_ids = alunos_visiveis(current_user)
    if not alunos_ids:
        return sucesso(
            data=[], total=0, message='Nenhum aluno disponivel para este professor'
        )

    alunos = [_serializar_aluno(a) for a in user_model.find_students_by_ids(alunos_ids)]
    return sucesso(data=alunos, total=len(alunos))


@teacher_blueprint.route('/crisis_alerts', methods=['GET'])
@token_required
@professor_required
def get_crisis_alerts(current_user):
    """Alunos em crise segundo o modelo de ML (janela recente)."""
    try:
        alunos_ids = alunos_visiveis(current_user)
        if not alunos_ids:
            return sucesso(data=[])

        minutos = max(1, min(request.args.get('minutos', 30, type=int) or 30, 1440))
        desde = datetime.datetime.utcnow() - datetime.timedelta(minutes=minutos)

        alertas = alert_model.find_by_alunos(alunos_ids, desde=desde)
        if not alertas:
            return sucesso(data=[])

        nomes = {
            u['_id']: u.get('nome', 'Aluno Desconhecido')
            for u in mongo.db.users.find({'_id': {'$in': list(alunos_ids)}}, {'nome': 1})
        }

        # Mantem apenas o alerta mais recente por aluno (ja vem ordenado desc)
        por_aluno = {}
        for alerta in alertas:
            aluno_id = alerta['aluno_id']
            if aluno_id in por_aluno:
                continue
            serializado = Alert.serializar(alerta)
            por_aluno[aluno_id] = {
                'aluno_id': serializado['aluno_id'],
                'nome': nomes.get(aluno_id, 'Aluno Desconhecido'),
                'heart_rate': serializado['bpm'],
                'bpm': serializado['bpm'],
                'gsr': serializado['gsr'],
                'movement_score': serializado['movement_score'],
                'severity': serializado['severity'],
                'timestamp': serializado['data_hora'],
                'motivo': serializado['motivo'],
                'resolvido': serializado['resolvido'],
                # ADR-010: severidade ainda nao validada clinicamente — o
                # professor precisa ver isso na propria tela de alerta de
                # crise, nao so num comentario de arquitetura.
                'modelo_validado': serializado['modelo_validado'],
            }

        return sucesso(data=list(por_aluno.values()))

    except Exception as e:
        return erro_interno(e, 'ao buscar alertas de crise')


def _historico_alertas(current_user, student_id, dias=30, ordem=1):
    """Historico de alertas de um aluno, com checagem de vinculo."""
    aluno_oid = to_object_id(student_id)
    if aluno_oid is None:
        return None, dados_invalidos('ID do aluno invalido')

    if not pode_ver_aluno(current_user, aluno_oid):
        return None, nao_autorizado('Acesso nao autorizado aos dados deste aluno')

    aluno = user_model.find_public_by_id(aluno_oid)
    if not aluno:
        return None, nao_encontrado('Aluno nao encontrado')

    desde = datetime.datetime.utcnow() - datetime.timedelta(days=dias)
    alertas = alert_model.find_by_aluno(aluno_oid, desde=desde, ordem=ordem)
    return (aluno, [Alert.serializar(a) for a in alertas]), None


@teacher_blueprint.route('/students/<string:student_id>/alerts_history', methods=['GET'])
@token_required
def get_student_alerts_history(current_user, student_id):
    """Historico de alertas dos ultimos 30 dias (ordem cronologica)."""
    try:
        dias = max(1, min(request.args.get('dias', 30, type=int) or 30, 365))
        resultado, resposta_erro = _historico_alertas(current_user, student_id, dias, ordem=1)
        if resposta_erro:
            return resposta_erro

        aluno, historico = resultado
        return sucesso(data={
            'aluno_nome': aluno.get('nome', 'Desconhecido'),
            'aluno_id': str(aluno['_id']),
            'total_alertas': len(historico),
            'historico': historico,
        })

    except Exception as e:
        return erro_interno(e, 'ao buscar historico de alertas')


@teacher_blueprint.route('/students/<string:student_id>/alert_history', methods=['GET'])
@token_required
def get_student_alert_history(current_user, student_id):
    """Historico de alertas (ordem decrescente).

    Mantido junto de alerts_history por compatibilidade com o dashboard, que
    consome os dois caminhos. Ambos leem a mesma fonte.
    """
    try:
        dias = max(1, min(request.args.get('dias', 30, type=int) or 30, 365))
        resultado, resposta_erro = _historico_alertas(current_user, student_id, dias, ordem=-1)
        if resposta_erro:
            return resposta_erro

        aluno, alertas = resultado
        return sucesso(
            data=alertas,
            success=True,
            student_name=aluno.get('nome', 'Desconhecido'),
            alerts=alertas,
            count=len(alertas),
        )

    except Exception as e:
        return erro_interno(e, 'ao buscar historico de alertas')


@teacher_blueprint.route('/students_average_grade', methods=['GET'])
@token_required
@professor_required
def get_students_average_grade(current_user):
    """Media das notas de todos os alunos do professor."""
    try:
        alunos_ids = alunos_visiveis(current_user)
        if not alunos_ids:
            return sucesso(data={'average': None, 'count': 0, 'students': 0})

        notas = [
            float(g['score'])
            for g in mongo.db.grades.find(
                {'student_id': {'$in': list(alunos_ids)}}, {'score': 1}
            )
            if isinstance(g.get('score'), (int, float)) and g['score'] >= 0
        ]

        if not notas:
            return sucesso(data={
                'average': None, 'count': 0, 'students': len(alunos_ids)
            })

        return sucesso(data={
            'average': round(sum(notas) / len(notas), 1),
            'count': len(notas),
            'students': len(alunos_ids),
        })

    except Exception as e:
        return erro_interno(e, 'ao calcular media das notas')


@teacher_blueprint.route('/dashboard', methods=['GET'])
@token_required
@professor_required
def get_dashboard(current_user):
    """Resumo consolidado para a tela inicial do professor."""
    try:
        turmas_ids = turmas_do_professor(current_user)
        alunos_ids = alunos_visiveis(current_user)

        desde = datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
        alertas_recentes = alert_model.find_by_alunos(alunos_ids, desde=desde) if alunos_ids else []

        return sucesso(data={
            'total_turmas': len(turmas_ids),
            'total_alunos': len(alunos_ids),
            'alertas_ativos': len([a for a in alertas_recentes if not a.get('resolvido')]),
            'alertas_recentes': [Alert.serializar(a) for a in alertas_recentes[:10]],
        })

    except Exception as e:
        return erro_interno(e, 'ao montar dashboard do professor')


@teacher_blueprint.route('/link-requests/pending', methods=['GET'])
@token_required
@professor_required
def get_pending_link_requests(current_user):
    """Pedidos de vinculo responsavel-filho pendentes, para alunos das
    turmas do professor — a fila que o professor confirma ou recusa.
    """
    try:
        alunos_ids = alunos_do_professor(current_user)
        pendentes = vinculo_model.pendentes_para_alunos(alunos_ids)
        if not pendentes:
            return sucesso(data=[], total=0)

        alunos_por_id = {
            a['_id']: a.get('nome', 'Desconhecido')
            for a in user_model.find_students_by_ids({v['aluno_id'] for v in pendentes})
        }
        responsaveis_por_id = {
            u['_id']: {'nome': u.get('nome'), 'email': u.get('email')}
            for u in mongo.db.users.find(
                {'_id': {'$in': list({v['responsavel_id'] for v in pendentes})}},
                {'nome': 1, 'email': 1},
            )
        }

        dados = []
        for vinculo in pendentes:
            serializado = Vinculo.serializar(vinculo)
            serializado['aluno_nome'] = alunos_por_id.get(vinculo['aluno_id'], 'Desconhecido')
            responsavel_info = responsaveis_por_id.get(vinculo['responsavel_id'], {})
            serializado['responsavel_nome'] = responsavel_info.get('nome')
            serializado['responsavel_email'] = responsavel_info.get('email')
            dados.append(serializado)

        return sucesso(data=dados, total=len(dados))

    except Exception as e:
        return erro_interno(e, 'ao buscar pedidos de vinculo pendentes')


def _decidir_vinculo(current_user, vinculo_id, aprovar):
    vinculo = vinculo_model.obter(vinculo_id)
    if vinculo is None:
        return nao_encontrado('Pedido de vinculo nao encontrado')

    # 404, nao 403: professor sem turma com este aluno nao deve nem
    # confirmar que o pedido existe — mesma filosofia das outras correcoes
    # de IDOR do projeto.
    if vinculo['aluno_id'] not in alunos_do_professor(current_user):
        return nao_encontrado('Pedido de vinculo nao encontrado')

    resultado = vinculo_model.decidir(vinculo_id, current_user['_id'], aprovar)
    if resultado.matched_count == 0:
        return dados_invalidos('Este pedido de vinculo ja foi decidido')

    if aprovar:
        user_model.link_child_to_parent(vinculo['responsavel_id'], vinculo['aluno_id'])
        return sucesso(message='Vinculo confirmado. O responsavel agora tem acesso aos dados do aluno.')

    return sucesso(message='Pedido de vinculo recusado.')


@teacher_blueprint.route('/link-requests/<string:vinculo_id>/confirm', methods=['PUT'])
@token_required
@professor_required
def confirm_link_request(current_user, vinculo_id):
    """Confirma que o responsavel realmente e responsavel por este aluno."""
    try:
        return _decidir_vinculo(current_user, vinculo_id, aprovar=True)
    except Exception as e:
        return erro_interno(e, 'ao confirmar vinculo')


@teacher_blueprint.route('/link-requests/<string:vinculo_id>/reject', methods=['PUT'])
@token_required
@professor_required
def reject_link_request(current_user, vinculo_id):
    """Recusa um pedido de vinculo — o responsavel nao ganha acesso algum."""
    try:
        return _decidir_vinculo(current_user, vinculo_id, aprovar=False)
    except Exception as e:
        return erro_interno(e, 'ao recusar vinculo')
