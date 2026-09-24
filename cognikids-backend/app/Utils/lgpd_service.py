"""
Portabilidade e exclusao de conta (LGPD art. 18, incisos V e VI).

Cobre os tres perfis (estudante, responsavel, professor). O aluno e o
titular com a maior superficie de dados pessoais sensiveis (biometria,
perfil funcional de acessibilidade, alertas de crise) e por isso e o que
recebe o tratamento mais completo.

O que fica de fora de proposito (nao e omissao):

- consent_events e accessibility_profile_events sao preservados mesmo
  quando o aluno e excluido. Os dois existem no codigo exatamente para
  sustentar prestacao de contas perante um comite de etica (ver docstring
  de consent_model.py). Depois da exclusao, o aluno_id neles vira um
  ObjectId orfao sem nome/email/perfil em lugar nenhum — deixa de ser dado
  pessoal identificavel por si so. Apagar esse rastro destruiria a propria
  garantia de auditoria que o sistema promete.
- Campos onde o usuario aparece so como ATOR de uma acao sobre o dado de
  OUTRA pessoa (graded_by, resolvido_por, atendido_por, approved_by,
  confirmado_por) nao sao apagados nem reescritos: sao metadados do
  registro de outra pessoa, nao dado pessoal de quem pediu a exclusao.
- Conteudo que um professor autorou para a turma (challenges, assignments,
  reports) permanece apos a exclusao da conta dele: apagar destruiria o
  historico pedagogico (notas, desafios concluidos) que pertence aos
  alunos, nao ao professor.
- Professor com turmas_ids nao vazio nao pode se autoexcluir (ver
  pode_excluir) — deixaria turmas sem dono e alunos vinculados a uma turma
  fantasma.
"""

import datetime
import logging

from bson.objectid import ObjectId

from app import mongo
from app.Utils.roles import ESTUDANTE, PROFESSOR, RESPONSAVEL, normalizar_tipo

logger = logging.getLogger(__name__)


def _serializar(valor):
    """Converte ObjectId/datetime para tipos serializaveis em JSON."""
    if isinstance(valor, ObjectId):
        return str(valor)
    if isinstance(valor, datetime.datetime):
        return valor.isoformat()
    if isinstance(valor, list):
        return [_serializar(v) for v in valor]
    if isinstance(valor, dict):
        return {k: _serializar(v) for k, v in valor.items()}
    return valor


def _serializar_doc(doc):
    return {k: v for k, v in _serializar(doc).items() if k not in ('senha', 'password')}


def exportar_dados(user):
    """Portabilidade (LGPD art. 18, V): todos os dados pessoais do titular,
    organizados por categoria."""
    uid = user['_id']
    tipo = normalizar_tipo(user.get('tipo'))

    dados = {
        'perfil': _serializar_doc(user),
        'notificacoes': [_serializar_doc(d) for d in mongo.db.notifications.find({'user_id': uid})],
        'mensagens_enviadas': [_serializar_doc(d) for d in mongo.db.messages.find({'from_user_id': uid})],
        'mensagens_recebidas': [_serializar_doc(d) for d in mongo.db.messages.find({'to_user_id': uid})],
        'topicos_forum': [_serializar_doc(d) for d in mongo.db.forum_topics.find({'author_id': uid})],
    }

    if tipo == ESTUDANTE:
        dados.update({
            'sentimentos': [_serializar_doc(d) for d in mongo.db.feelings.find({'aluno_id': uid})],
            'criacoes_galeria': [_serializar_doc(d) for d in mongo.db.gallery_creations.find({'aluno_id': uid})],
            'conclusoes_desafios': [_serializar_doc(d) for d in mongo.db.challenge_completions.find({'aluno_id': uid})],
            'pedidos_pausa': [_serializar_doc(d) for d in mongo.db.break_requests.find({'aluno_id': uid})],
            'metas': [_serializar_doc(d) for d in mongo.db.goals.find({'student_id': uid})],
            'notas': [_serializar_doc(d) for d in mongo.db.grades.find({'student_id': uid})],
            'perguntas': [_serializar_doc(d) for d in mongo.db.questions.find({'aluno_id': uid})],
            'perfil_acessibilidade': _serializar_doc(mongo.db.accessibility_profiles.find_one({'aluno_id': uid}) or {}),
            'historico_acessibilidade': [_serializar_doc(d) for d in mongo.db.accessibility_profile_events.find({'aluno_id': uid})],
            'consentimento_atual': _serializar_doc(mongo.db.consents.find_one({'aluno_id': uid}) or {}),
            'historico_consentimento': [_serializar_doc(d) for d in mongo.db.consent_events.find({'aluno_id': uid})],
            'alertas': [_serializar_doc(d) for d in mongo.db.alerts.find({'aluno_id': uid})],
            'registros_iot': [_serializar_doc(d) for d in mongo.db.registros_iot.find({'aluno_id': uid})],
            'dispositivos': [_serializar_doc(d) for d in mongo.db.dispositivos.find({'aluno_id': uid})],
            'vinculos_com_responsaveis': [_serializar_doc(d) for d in mongo.db.vinculos_pendentes.find({'aluno_id': uid})],
        })
    elif tipo == RESPONSAVEL:
        dados['vinculos_pedidos'] = [_serializar_doc(d) for d in mongo.db.vinculos_pendentes.find({'responsavel_id': uid})]
    elif tipo == PROFESSOR:
        dados.update({
            'turmas': [_serializar_doc(d) for d in mongo.db.turmas.find({'teacher_id': uid})],
            'desafios_criados': [_serializar_doc(d) for d in mongo.db.challenges.find({'created_by': uid})],
            'avaliacoes_criadas': [_serializar_doc(d) for d in mongo.db.assignments.find({'created_by': uid})],
            'relatorios': [_serializar_doc(d) for d in mongo.db.reports.find({'teacher_id': uid})],
        })

    return dados


def pode_excluir(user):
    """(bool, motivo|None) — professor com turmas ativas precisa transferir
    ou excluir as turmas antes de excluir a propria conta."""
    tipo = normalizar_tipo(user.get('tipo'))
    if tipo == PROFESSOR and user.get('turmas_ids'):
        return False, (
            'Voce ainda e responsavel por turmas. Transfira ou exclua suas '
            'turmas antes de excluir sua conta.'
        )
    return True, None


def excluir_conta(user):
    """Exclusao (LGPD art. 18, VI). O chamador deve checar pode_excluir()
    antes de invocar esta funcao."""
    uid = user['_id']
    tipo = normalizar_tipo(user.get('tipo'))

    mongo.db.notifications.delete_many({'user_id': uid})
    mongo.db.messages.delete_many({'$or': [{'from_user_id': uid}, {'to_user_id': uid}]})
    mongo.db.forum_topics.delete_many({'author_id': uid})

    if tipo == ESTUDANTE:
        mongo.db.feelings.delete_many({'aluno_id': uid})
        mongo.db.gallery_creations.delete_many({'aluno_id': uid})
        mongo.db.challenge_completions.delete_many({'aluno_id': uid})
        mongo.db.break_requests.delete_many({'aluno_id': uid})
        mongo.db.goals.delete_many({'student_id': uid})
        mongo.db.grades.delete_many({'student_id': uid})
        mongo.db.questions.delete_many({'aluno_id': uid})
        mongo.db.accessibility_profiles.delete_many({'aluno_id': uid})
        mongo.db.consents.delete_many({'aluno_id': uid})
        mongo.db.registros_iot.delete_many({'aluno_id': uid})
        mongo.db.alerts.delete_many({'aluno_id': uid})
        mongo.db.dispositivos.delete_many({'aluno_id': uid})
        mongo.db.vinculos_pendentes.delete_many({'aluno_id': uid})

        # dono da turma e' o professor; o aluno so' sai das listas dele
        mongo.db.turmas.update_many(
            {'alunos_ids': uid}, {'$pull': {'alunos_ids': uid}}
        )
        mongo.db.turmas.update_many(
            {'students': uid}, {'$pull': {'students': uid}}
        )

        # tira o aluno da lista de filhos de qualquer responsavel
        mongo.db.users.update_many({'filhos_ids': uid}, {'$pull': {'filhos_ids': uid}})

        _notificar_satelite(uid)

    elif tipo == RESPONSAVEL:
        mongo.db.vinculos_pendentes.delete_many({'responsavel_id': uid})

    # PROFESSOR: sem limpeza adicional alem do usuario em si — ver docstring
    # do modulo sobre o conteudo autorado que permanece.

    resultado = mongo.db.users.delete_one({'_id': uid})
    logger.info('Conta excluida (LGPD art. 18, VI): %s (%s)', uid, tipo)
    return resultado


def _notificar_satelite(aluno_oid):
    """Mesma cascata core->satelite da revogacao de consentimento
    (consent_model._notificar_satelite_da_revogacao) — exclusao de conta
    tambem precisa apagar student_graphs/telemetry_events no satelite."""
    from app.Utils.satellite_client import notificar_revogacao_biometrica

    try:
        notificar_revogacao_biometrica(str(aluno_oid))
    except Exception as e:
        logger.warning(
            'Falha inesperada ao notificar o satelite na exclusao de conta: %s', e
        )
