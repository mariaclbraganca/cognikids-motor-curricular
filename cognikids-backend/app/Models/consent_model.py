"""
Consentimento granular e revogavel (LGPD).

O tratamento de dados pessoais de criancas exige consentimento especifico e
em destaque dado por ao menos um dos pais ou responsavel legal (LGPD art.
14, §1o). Dados de saude e biometricos sao categoria especial (art. 11).

Por isso o consentimento aqui e:

- Granular: quatro finalidades independentes. Negar coleta biometrica nao
  impede a crianca de usar o app.
- Revogavel: revogar e tao facil quanto conceder (art. 8o, §5o), e o efeito
  e imediato — a ingestao IoT passa a rejeitar os dados daquele aluno.
- Auditavel: cada concessao e revogacao vira um registro imutavel em
  consent_events, com data e autor. E o que sustenta a prestacao de contas
  perante um comite de etica.

O documento vigente fica em 'consents' (um por aluno); o rastro completo
fica em 'consent_events'.
"""

import datetime
import logging

from bson.objectid import ObjectId

from app import mongo

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Finalidades
# --------------------------------------------------------------------------

USO_APP = 'uso_app'
COLETA_BIOMETRICA = 'coleta_biometrica'
COMPARTILHAR_ESCOLA = 'compartilhar_escola'
USO_PESQUISA = 'uso_pesquisa'

FINALIDADES = {
    USO_APP: {
        'titulo': 'Usar o aplicativo',
        'descricao': (
            'Seu filho pode entrar no app, registrar como esta se sentindo e '
            'pedir uma pausa quando precisar.'
        ),
        'obrigatorio': True,
        'implica': [],
    },
    COLETA_BIOMETRICA: {
        'titulo': 'Coletar dados da pulseira',
        'descricao': (
            'A pulseira mede batimentos cardiacos e movimento. Sem isso, o app '
            'continua funcionando, mas nao identifica sinais de desregulacao.'
        ),
        'obrigatorio': False,
        'implica': [USO_APP],
    },
    COMPARTILHAR_ESCOLA: {
        'titulo': 'Compartilhar com a escola',
        'descricao': (
            'O professor da turma pode ver os registros e os alertas do seu '
            'filho para apoia-lo durante a aula.'
        ),
        'obrigatorio': False,
        'implica': [USO_APP],
    },
    USO_PESQUISA: {
        'titulo': 'Usar os dados em pesquisa',
        'descricao': (
            'Indisponivel no momento. O uso de dados em pesquisa com criancas '
            'depende de aprovacao de um Comite de Etica em Pesquisa (CEP), que '
            'ainda nao foi obtida. Nenhum dado do seu filho e usado em pesquisa '
            'hoje.'
        ),
        'obrigatorio': False,
        'implica': [],
        'disponivel': False,
    },
}

# Finalidades que o sistema ainda nao pode oferecer, e por que. Ficam visiveis
# e desabilitadas em vez de sumirem da tela: some-las esconderia do responsavel
# que a finalidade existiu, e quebraria a leitura dos consent_events ja
# gravados.
FINALIDADES_INDISPONIVEIS = {
    fid for fid, meta in FINALIDADES.items() if not meta.get('disponivel', True)
}

VERSAO_TERMO = '1.0.0'


def _eliminar_dado_biometrico(aluno_oid):
    """Apaga o historico biometrico bruto do aluno (registros_iot + alerts).

    Chamado quando COLETA_BIOMETRICA passa de concedido para revogado —
    antes desta correcao, revogar so mudava a flag do consentimento; todo o
    historico de BPM/GSR (dado sensivel de crianca, art. 11 da LGPD)
    continuava gravado indefinidamente, sem nenhuma rotina de eliminacao.
    Nao ha finalidade legitima remanescente para manter esse dado bruto uma
    vez que a coleta deixou de ser autorizada — por isso eliminacao, nao so
    anonimizacao.

    So cobre o banco do CORE. O satelite deriva do mesmo dado comportamental
    o proprio grafo de conhecimento (student_graphs) e a telemetria bruta
    (telemetry_events) — ver _notificar_satelite_da_revogacao logo abaixo,
    que fecha essa lacuna (documentada como aberta na ADR-008/ADR-010) numa
    chamada best-effort separada, para nao acoplar o core ao satelite.
    """
    resultado_registros = mongo.db.registros_iot.delete_many({'aluno_id': aluno_oid})
    resultado_alertas = mongo.db.alerts.delete_many({'aluno_id': aluno_oid})
    logger.info(
        'Consentimento de coleta biometrica revogado para aluno %s: '
        '%d registros_iot e %d alerts eliminados',
        aluno_oid, resultado_registros.deleted_count, resultado_alertas.deleted_count,
    )
    _notificar_satelite_da_revogacao(aluno_oid)


def _notificar_satelite_da_revogacao(aluno_oid):
    """Cascata core->satelite (ADR-008/ADR-010): pede ao satelite para
    apagar student_graphs/telemetry_events deste aluno.

    Best-effort de proposito — nunca pode impedir nem reverter a eliminacao
    ja feita no core, mesmo que o satelite esteja fora do ar (CLAUDE.md
    secao 2: o core continua funcionando sem o satelite). Import local
    evita qualquer acoplamento de import-time entre os dois servicos.
    """
    from app.Utils.satellite_client import notificar_revogacao_biometrica

    try:
        notificar_revogacao_biometrica(str(aluno_oid))
    except Exception as e:
        # notificar_revogacao_biometrica ja trata as proprias falhas de
        # rede internamente — este except e' so uma segunda rede de
        # seguranca para nunca deixar a cascata quebrar a revogacao no core.
        logger.warning('Falha inesperada ao notificar o satelite: %s', e)


def _to_object_id(valor):
    if isinstance(valor, ObjectId):
        return valor
    try:
        return ObjectId(valor)
    except Exception:
        return None


class Consent:
    def obter(self, aluno_id):
        """Documento de consentimento vigente do aluno (ou None)."""
        oid = _to_object_id(aluno_id)
        if oid is None:
            return None
        return mongo.db.consents.find_one({'aluno_id': oid})

    def estado(self, aluno_id):
        """Mapa {finalidade: bool} do que esta concedido agora."""
        documento = self.obter(aluno_id) or {}
        concedidos = documento.get('finalidades', {})
        return {f: bool(concedidos.get(f)) for f in FINALIDADES}

    def permite(self, aluno_id, finalidade):
        """Ha consentimento vigente para esta finalidade?"""
        return self.estado(aluno_id).get(finalidade, False)

    def registrar(self, aluno_id, finalidades, autor_id, ip=None):
        """Grava o consentimento e o evento de auditoria.

        Args:
            finalidades: {finalidade: bool}
            autor_id: responsavel que assinou

        Returns:
            (estado_final, avisos)
        """
        aluno_oid = _to_object_id(aluno_id)
        autor_oid = _to_object_id(autor_id)
        if aluno_oid is None or autor_oid is None:
            raise ValueError('IDs invalidos ao registrar consentimento')

        anterior = self.estado(aluno_id)
        novo = dict(anterior)
        avisos = []

        for finalidade, concedido in (finalidades or {}).items():
            if finalidade not in FINALIDADES:
                continue

            # Finalidade indisponivel nunca pode ser concedida, venha o pedido
            # de onde vier. 'uso_pesquisa' prometia ao responsavel "dados sem
            # identificacao" e NADA no codigo desidentifica nada — a frase era
            # falsa. Alem disso a constante nunca era lida por codigo de
            # producao: quem marcava sim e quem marcava nao recebiam tratamento
            # identico. Consentimento que nao altera o comportamento do sistema
            # nao e consentimento. Pesquisa com menores exige ainda CEP/CONEP
            # (Res. CNS 466/2012 e 510/2016), TCLE do responsavel e TALE da
            # propria crianca — nada disso existe hoje.
            if finalidade in FINALIDADES_INDISPONIVEIS:
                if concedido:
                    avisos.append(
                        f"'{FINALIDADES[finalidade]['titulo']}' esta indisponivel "
                        'e nao foi ativado.'
                    )
                novo[finalidade] = False
                continue

            novo[finalidade] = bool(concedido)

        # Dependencias: negar uma finalidade derruba as que dependem dela.
        # Ex.: sem uso do app, nao ha como coletar biometria.
        for finalidade, meta in FINALIDADES.items():
            if not novo.get(finalidade):
                continue
            faltando = [d for d in meta['implica'] if not novo.get(d)]
            if faltando:
                novo[finalidade] = False
                titulos = ', '.join(FINALIDADES[d]['titulo'] for d in faltando)
                avisos.append(
                    f"'{meta['titulo']}' depende de: {titulos}. Nao foi ativado."
                )

        agora = datetime.datetime.utcnow()

        mongo.db.consents.update_one(
            {'aluno_id': aluno_oid},
            {'$set': {
                'aluno_id': aluno_oid,
                'finalidades': novo,
                'versao_termo': VERSAO_TERMO,
                'atualizado_em': agora,
                'atualizado_por': autor_oid,
            }},
            upsert=True,
        )

        # Rastro de auditoria: apenas o que mudou
        mudancas = {
            f: {'de': anterior.get(f, False), 'para': novo[f]}
            for f in FINALIDADES
            if anterior.get(f, False) != novo[f]
        }

        if mudancas:
            mongo.db.consent_events.insert_one({
                'aluno_id': aluno_oid,
                'autor_id': autor_oid,
                'mudancas': mudancas,
                'versao_termo': VERSAO_TERMO,
                'data_hora': agora,
                'ip': ip,
            })

        # Efeito real da revogacao sobre o dado ja coletado — nao so sobre
        # a visibilidade futura. COMPARTILHAR_ESCOLA fica de fora de
        # proposito: revogar o compartilhamento com a escola nao significa
        # que o dado deixou de ter finalidade legitima (o app/responsavel
        # continua usando), so que o professor deixa de ve-lo — isso ja e
        # aplicado via `alunos_visiveis`/`filtrar_por_consentimento`.
        mudanca_biometria = mudancas.get(COLETA_BIOMETRICA)
        if mudanca_biometria and mudanca_biometria['de'] and not mudanca_biometria['para']:
            _eliminar_dado_biometrico(aluno_oid)

        return novo, avisos

    def revogar_tudo(self, aluno_id, autor_id, ip=None):
        """Revoga todas as finalidades de uma vez."""
        return self.registrar(
            aluno_id, {f: False for f in FINALIDADES}, autor_id, ip
        )

    def historico(self, aluno_id, limite=100):
        """Rastro de auditoria do consentimento."""
        oid = _to_object_id(aluno_id)
        if oid is None:
            return []
        return list(
            mongo.db.consent_events.find({'aluno_id': oid})
            .sort('data_hora', -1)
            .limit(limite)
        )

    @staticmethod
    def termo_publico():
        """Texto das finalidades para exibir ao responsavel."""
        return {
            'versao': VERSAO_TERMO,
            'finalidades': [
                {
                    'id': fid,
                    'titulo': meta['titulo'],
                    'descricao': meta['descricao'],
                    'obrigatorio': meta['obrigatorio'],
                    'depende_de': meta['implica'],
                    # A UI mostra a finalidade desabilitada, nao a esconde.
                    'disponivel': meta.get('disponivel', True),
                }
                for fid, meta in FINALIDADES.items()
            ],
        }

    @staticmethod
    def serializar_evento(evento):
        data_hora = evento.get('data_hora')
        return {
            '_id': str(evento.get('_id')),
            'aluno_id': str(evento.get('aluno_id')),
            'autor_id': str(evento.get('autor_id')),
            'mudancas': evento.get('mudancas', {}),
            'versao_termo': evento.get('versao_termo'),
            'data_hora': data_hora.isoformat() if data_hora else None,
        }
