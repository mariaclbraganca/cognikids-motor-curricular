"""
Pedido de pausa.

O aluno sinaliza que precisa de um tempo; o professor da turma recebe e
atende. E a via pela qual a crianca participa ativamente do sistema, em vez
de apenas ser medida por ele.
"""

import datetime
import logging

from flask import Blueprint, request

from app import mongo
from app.Models.break_request_model import BreakRequest, RESULTADOS
from app.Utils.authz import alunos_visiveis, pode_ver_aluno, to_object_id
from app.Utils.decorators import estudante_required, professor_required, token_required
from app.Utils.responses import (
    dados_invalidos,
    erro_interno,
    nao_autorizado,
    nao_encontrado,
    sucesso,
)

logger = logging.getLogger(__name__)

break_blueprint = Blueprint('break', __name__)
break_model = BreakRequest()


def _estrategias_do_kit(aluno_id):
    """Estrategias cadastradas pelo responsavel no kit de apoio."""
    kit = mongo.db.support_kits.find_one({'aluno_id': to_object_id(aluno_id)})
    if not kit:
        return []

    bruto = kit.get('estrategias_calmantes', '')
    if isinstance(bruto, list):
        return [str(e).strip() for e in bruto if str(e).strip()]

    # Campo historicamente textual: aceita itens separados por linha ou virgula
    texto = str(bruto).replace('\n', ',')
    return [parte.strip() for parte in texto.split(',') if parte.strip()]


@break_blueprint.route('/options', methods=['GET'])
@token_required
@estudante_required
def get_options(current_user):
    """Estrategias sugeridas ao aluno, ordenadas pelo que ja funcionou.

    As opcoes vem do kit de apoio preenchido pelo responsavel — nunca sao
    genericas. A ordenacao por eficacia segue o padrao dos aplicativos de
    regulacao emocional com validacao publicada.
    """
    try:
        aluno_id = current_user['_id']
        estrategias = _estrategias_do_kit(aluno_id)
        eficacia = break_model.eficacia_por_estrategia(aluno_id)

        opcoes = []
        for estrategia in estrategias:
            registro = eficacia.get(estrategia, {'ajudou': 0, 'total': 0})
            opcoes.append({
                'estrategia': estrategia,
                'ajudou': registro['ajudou'],
                'total': registro['total'],
            })

        opcoes.sort(key=lambda o: (o['ajudou'], o['total']), reverse=True)

        return sucesso(data={
            'opcoes': opcoes,
            # Avisar sem escolher precisa ser sempre possivel: em
            # desregulacao, escolher ja pode ser demais.
            'permite_sem_escolher': True,
        })

    except Exception as e:
        return erro_interno(e, 'ao listar opcoes de pausa')


@break_blueprint.route('', methods=['POST'])
@token_required
@estudante_required
def request_break(current_user):
    """(ALUNO) Pede uma pausa. A estrategia e opcional."""
    try:
        data = request.get_json(silent=True) or {}
        estrategia = data.get('estrategia')

        if estrategia is not None:
            estrategia = str(estrategia).strip() or None

        resultado = break_model.criar(current_user['_id'], estrategia)

        # Notifica os professores da turma (falha aqui nao invalida o pedido)
        try:
            _notificar_professores(current_user, str(resultado.inserted_id))
        except Exception as e:
            logger.warning('Falha ao notificar professores da pausa: %s', e)

        return sucesso(
            message='Avisamos a professora. Voce pode ficar tranquilo.',
            status_code=201,
            pedido_id=str(resultado.inserted_id),
        )

    except Exception as e:
        return erro_interno(e, 'ao registrar pedido de pausa')


def _notificar_professores(aluno, pedido_id):
    """Cria notificacao para os professores das turmas do aluno."""
    from app.Controllers.notification_controller import NotificationService

    turma_id = aluno.get('turma_id')
    if not turma_id:
        return

    professores = mongo.db.turmas.find({'_id': turma_id}, {'teacher_id': 1})
    for turma in professores:
        if not turma.get('teacher_id'):
            continue
        NotificationService.notify_system_announcement(
            str(turma['teacher_id']),
            'Pedido de pausa',
            f"{aluno.get('nome', 'Um aluno')} pediu uma pausa.",
            priority='high',
        )


@break_blueprint.route('/mine', methods=['GET'])
@token_required
@estudante_required
def my_breaks(current_user):
    """(ALUNO) Historico dos proprios pedidos."""
    try:
        pedidos = break_model.historico_do_aluno(current_user['_id'], limite=20)
        return sucesso(data=[BreakRequest.serializar(p) for p in pedidos])
    except Exception as e:
        return erro_interno(e, 'ao listar meus pedidos de pausa')


@break_blueprint.route('/pending', methods=['GET'])
@token_required
@professor_required
def pending_breaks(current_user):
    """(PROFESSOR) Pedidos em aberto dos alunos das suas turmas.

    Usa `alunos_visiveis` (nao `alunos_do_professor` puro) para aplicar o
    consentimento de compartilhamento com a escola — sem isso, um aluno cujo
    responsavel revogou o compartilhamento continuava aparecendo aqui com
    nome, mesmo estando fora da visao do professor em todo o resto do
    sistema.
    """
    try:
        alunos_ids = alunos_visiveis(current_user)
        if not alunos_ids:
            return sucesso(data=[])

        pedidos = break_model.abertos_por_alunos(alunos_ids)

        nomes = {
            u['_id']: u.get('nome', 'Aluno')
            for u in mongo.db.users.find({'_id': {'$in': list(alunos_ids)}}, {'nome': 1})
        }

        data = []
        for pedido in pedidos:
            serializado = BreakRequest.serializar(pedido)
            serializado['aluno_nome'] = nomes.get(pedido['aluno_id'], 'Aluno')
            data.append(serializado)

        return sucesso(data=data, count=len(data))

    except Exception as e:
        return erro_interno(e, 'ao listar pedidos de pausa pendentes')


@break_blueprint.route('/<string:pedido_id>/acknowledge', methods=['PUT'])
@token_required
@professor_required
def acknowledge(current_user, pedido_id):
    """(PROFESSOR) Confirma que viu e esta atendendo o pedido."""
    try:
        pedido = break_model.find_by_id(pedido_id)
        if not pedido:
            return nao_encontrado('Pedido de pausa nao encontrado')

        if not pode_ver_aluno(current_user, pedido['aluno_id']):
            return nao_autorizado('Este aluno nao pertence as suas turmas')

        break_model.marcar_atendido(pedido_id, current_user['_id'])
        return sucesso(message='Pedido marcado como atendido')

    except Exception as e:
        return erro_interno(e, 'ao atender pedido de pausa')


@break_blueprint.route('/<string:pedido_id>/close', methods=['PUT'])
@token_required
def close(current_user, pedido_id):
    """Encerra o pedido, registrando se a estrategia ajudou.

    Tanto o proprio aluno quanto o professor podem encerrar.
    """
    try:
        pedido = break_model.find_by_id(pedido_id)
        if not pedido:
            return nao_encontrado('Pedido de pausa nao encontrado')

        if not pode_ver_aluno(current_user, pedido['aluno_id']):
            return nao_autorizado('Acesso nao autorizado a este pedido')

        data = request.get_json(silent=True) or {}
        resultado = data.get('resultado', 'nao_informado')

        if resultado not in RESULTADOS:
            return dados_invalidos(
                f'resultado deve ser um de: {", ".join(RESULTADOS)}'
            )

        break_model.encerrar(pedido_id, resultado)
        return sucesso(message='Pedido encerrado')

    except Exception as e:
        return erro_interno(e, 'ao encerrar pedido de pausa')


@break_blueprint.route('/student/<string:aluno_id>', methods=['GET'])
@token_required
def student_breaks(current_user, aluno_id):
    """Historico de pausas de um aluno (professor ou responsavel)."""
    try:
        aluno_oid = to_object_id(aluno_id)
        if aluno_oid is None:
            return dados_invalidos('ID do aluno invalido')

        if not pode_ver_aluno(current_user, aluno_oid):
            return nao_autorizado('Acesso nao autorizado aos dados deste aluno')

        dias = max(1, min(request.args.get('dias', 30, type=int) or 30, 365))
        desde = datetime.datetime.utcnow() - datetime.timedelta(days=dias)

        pedidos = break_model.historico_do_aluno(aluno_oid, desde=desde)

        return sucesso(
            data=[BreakRequest.serializar(p) for p in pedidos],
            eficacia=break_model.eficacia_por_estrategia(aluno_oid, dias),
        )

    except Exception as e:
        return erro_interno(e, 'ao consultar historico de pausas')
