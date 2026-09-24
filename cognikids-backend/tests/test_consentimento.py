"""
Consentimento granular (LGPD).

Cobre o que sustenta a base legal do sistema: quem pode consentir, o efeito
imediato da revogacao sobre a coleta, e a auditabilidade das mudancas.
"""

import pytest


class TestTermo:
    def test_lista_finalidades(self, responsavel):
        r = responsavel.get('/api/consent/terms')
        assert r.status_code == 200

        dados = r.get_json()['data']
        ids = {f['id'] for f in dados['finalidades']}
        assert ids == {
            'uso_app', 'coleta_biometrica', 'compartilhar_escola', 'uso_pesquisa'
        }

    def test_cada_finalidade_tem_descricao_em_linguagem_simples(self, responsavel):
        dados = responsavel.get('/api/consent/terms').get_json()['data']
        for finalidade in dados['finalidades']:
            assert finalidade['descricao']
            assert finalidade['titulo']


class TestConcessao:
    def test_responsavel_concede(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': True, 'coleta_biometrica': True},
        })
        assert r.status_code == 200

        finalidades = r.get_json()['data']['finalidades']
        assert finalidades['uso_app'] is True
        assert finalidades['coleta_biometrica'] is True

    def test_negar_por_padrao(self, vinculo_responsavel, estudante):
        """Sem consentimento registrado, nada esta autorizado."""
        r = vinculo_responsavel.get(f'/api/consent/{estudante.id}')
        assert r.status_code == 200
        assert all(v is False for v in r.get_json()['data']['finalidades'].values())

    def test_dependencia_bloqueia_finalidade(self, vinculo_responsavel, estudante):
        """Coleta biometrica sem uso do app nao pode ser ativada."""
        r = vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': False, 'coleta_biometrica': True},
        })
        assert r.status_code == 200
        assert r.get_json()['data']['finalidades']['coleta_biometrica'] is False
        assert r.get_json()['avisos']

    def test_recusar_pesquisa_nao_impede_o_resto(self, vinculo_responsavel, estudante):
        """Recusa de pesquisa nao pode ter consequencia — exigencia etica."""
        r = vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {
                'uso_app': True, 'coleta_biometrica': True, 'uso_pesquisa': False,
            },
        })
        finalidades = r.get_json()['data']['finalidades']
        assert finalidades['uso_app'] is True
        assert finalidades['coleta_biometrica'] is True
        assert finalidades['uso_pesquisa'] is False

    def test_rejeita_finalidade_desconhecida(self, vinculo_responsavel, estudante):
        r = vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'vender_dados': True},
        })
        assert r.status_code == 400


class TestQuemPodeConsentir:
    def test_professor_nao_concede(self, professor, turma, estudante):
        r = professor.put(f'/api/consent/{estudante.id}',
                          json={'finalidades': {'uso_app': True}})
        assert r.status_code == 403

    def test_aluno_nao_concede_por_si(self, estudante):
        r = estudante.put(f'/api/consent/{estudante.id}',
                          json={'finalidades': {'uso_app': True}})
        assert r.status_code == 403

    def test_responsavel_nao_concede_por_filho_alheio(self, responsavel, estudante):
        r = responsavel.put(f'/api/consent/{estudante.id}',
                            json={'finalidades': {'uso_app': True}})
        assert r.status_code == 403


class TestRevogacao:
    def test_revogar_tudo(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': True, 'coleta_biometrica': True},
        })

        r = vinculo_responsavel.delete(f'/api/consent/{estudante.id}')
        assert r.status_code == 200
        assert all(v is False for v in r.get_json()['data']['finalidades'].values())

    def test_revogacao_interrompe_ingestao_imediatamente(
        self, client, api_key_headers, vinculo_responsavel, estudante, dispositivo, db
    ):
        """O efeito precisa ser imediato — art. 8o, §5o."""
        antes = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 90},
        })
        assert antes.status_code == 201

        vinculo_responsavel.delete(f'/api/consent/{estudante.id}')

        depois = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 90},
        })
        assert depois.status_code == 403
        # A revogacao elimina o historico ja coletado, nao so bloqueia
        # ingestao futura — sem finalidade legitima para reter dado
        # biometrico de uma crianca cuja coleta deixou de ser autorizada.
        assert db.registros_iot.count_documents({}) == 0

    def test_revogacao_elimina_alertas_biometricos_existentes(
        self, vinculo_responsavel, estudante, db
    ):
        vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': True, 'coleta_biometrica': True},
        })

        db.alerts.insert_one({'aluno_id': estudante.oid, 'severity': 'high', 'resolvido': False})
        db.registros_iot.insert_one({'aluno_id': estudante.oid, 'dados_biometricos': {'bpm': 140}})
        assert db.alerts.count_documents({'aluno_id': estudante.oid}) == 1
        assert db.registros_iot.count_documents({'aluno_id': estudante.oid}) == 1

        vinculo_responsavel.delete(f'/api/consent/{estudante.id}')

        assert db.alerts.count_documents({'aluno_id': estudante.oid}) == 0
        assert db.registros_iot.count_documents({'aluno_id': estudante.oid}) == 0

    def test_revogacao_notifica_o_satelite(self, vinculo_responsavel, estudante, monkeypatch):
        """Cascata core->satelite (ADR-008/ADR-010): apagar so no core deixa
        rastro equivalente (student_graphs/telemetry_events) vivo no satelite.
        """
        chamadas = []
        monkeypatch.setattr(
            'app.Utils.satellite_client.notificar_revogacao_biometrica',
            lambda aluno_id: chamadas.append(aluno_id),
        )

        vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': True, 'coleta_biometrica': True},
        })
        vinculo_responsavel.delete(f'/api/consent/{estudante.id}')

        assert chamadas == [str(estudante.oid)]

    def test_revogacao_nao_falha_se_satelite_estiver_fora_do_ar(
        self, vinculo_responsavel, estudante, monkeypatch, db
    ):
        """CLAUDE.md secao 2: o core continua funcionando sem o satelite —
        a cascata e' best-effort, nunca pode quebrar a revogacao no core.
        """
        def _fora_do_ar(aluno_id):
            raise ConnectionError('satelite fora do ar (simulado)')

        monkeypatch.setattr(
            'app.Utils.satellite_client.notificar_revogacao_biometrica', _fora_do_ar
        )

        vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': True, 'coleta_biometrica': True},
        })
        db.registros_iot.insert_one({'aluno_id': estudante.oid, 'dados_biometricos': {'bpm': 100}})

        r = vinculo_responsavel.delete(f'/api/consent/{estudante.id}')

        assert r.status_code == 200, (
            'REGRESSAO CRITICA: satelite fora do ar quebrou a revogacao no core'
        )
        assert db.registros_iot.count_documents({'aluno_id': estudante.oid}) == 0

    def test_revogar_compartilhamento_isolado_nao_apaga_biometria(
        self, vinculo_responsavel, estudante, db
    ):
        """Revogar so o compartilhamento com a escola nao apaga dado —
        so tira a visibilidade do professor; a coleta biometrica continua
        autorizada e legitima."""
        vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'finalidades': {'uso_app': True, 'coleta_biometrica': True, 'compartilhar_escola': True},
        })
        db.registros_iot.insert_one({'aluno_id': estudante.oid, 'dados_biometricos': {'bpm': 100}})

        vinculo_responsavel.put(f'/api/consent/{estudante.id}', json={
            'compartilhar_escola': False,
        })

        assert db.registros_iot.count_documents({'aluno_id': estudante.oid}) == 1


class TestEnforcementDaColeta:
    def test_ingestao_bloqueada_sem_consentimento(
        self, client, api_key_headers, estudante, db
    ):
        db.consents.delete_many({})
        dispositivo_id = db.dispositivos.insert_one({
            'aluno_id': estudante.oid, 'status': 'ativo',
        }).inserted_id

        r = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo_id),
            'dados_biometricos': {'bpm': 95},
        })
        assert r.status_code == 403
        assert db.registros_iot.count_documents({}) == 0

    def test_ingestao_liberada_com_consentimento(
        self, client, api_key_headers, estudante, dispositivo, db
    ):
        r = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 95},
        })
        assert r.status_code == 201
        assert db.registros_iot.count_documents({}) == 1


class TestEnforcementDoCompartilhamento:
    def test_professor_nao_ve_aluno_sem_consentimento(
        self, professor, turma, estudante, db
    ):
        """Vinculo pedagogico nao basta: precisa de base legal."""
        db.consents.update_one(
            {'aluno_id': estudante.oid},
            {'$set': {'finalidades.compartilhar_escola': False}},
        )

        r = professor.get('/api/teachers/all_students')
        assert r.status_code == 200
        assert r.get_json()['data'] == []

    def test_professor_nao_le_alertas_sem_consentimento(
        self, professor, turma, estudante, alerta, db
    ):
        db.consents.update_one(
            {'aluno_id': estudante.oid},
            {'$set': {'finalidades.compartilhar_escola': False}},
        )

        assert professor.get(
            f'/api/teachers/students/{estudante.id}/alerts_history'
        ).status_code == 403

    def test_professor_volta_a_ver_apos_reconsentimento(
        self, professor, turma, estudante, db
    ):
        db.consents.update_one(
            {'aluno_id': estudante.oid},
            {'$set': {'finalidades.compartilhar_escola': False}},
        )
        assert professor.get('/api/teachers/all_students').get_json()['data'] == []

        db.consents.update_one(
            {'aluno_id': estudante.oid},
            {'$set': {'finalidades.compartilhar_escola': True}},
        )
        assert professor.get('/api/teachers/all_students').get_json()['total'] == 1

    def test_responsavel_ve_o_filho_independente_do_compartilhamento(
        self, vinculo_responsavel, estudante, db
    ):
        """Revogar o compartilhamento com a escola nao afeta a familia."""
        db.consents.update_one(
            {'aluno_id': estudante.oid},
            {'$set': {'finalidades.compartilhar_escola': False}},
            upsert=True,
        )
        assert vinculo_responsavel.get('/api/parents/children').get_json()['total'] == 1


class TestAuditoria:
    def test_registra_historico_de_mudancas(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/consent/{estudante.id}',
                                json={'finalidades': {'uso_app': True}})
        vinculo_responsavel.delete(f'/api/consent/{estudante.id}')

        r = vinculo_responsavel.get(f'/api/consent/{estudante.id}/history')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 2

    def test_historico_registra_de_para(self, vinculo_responsavel, estudante):
        vinculo_responsavel.put(f'/api/consent/{estudante.id}',
                                json={'finalidades': {'uso_app': True}})

        evento = vinculo_responsavel.get(
            f'/api/consent/{estudante.id}/history'
        ).get_json()['data'][0]

        assert evento['mudancas']['uso_app'] == {'de': False, 'para': True}
        assert evento['autor_id']
        assert evento['data_hora']

    def test_professor_nao_acessa_historico(self, professor, turma, estudante):
        assert professor.get(
            f'/api/consent/{estudante.id}/history'
        ).status_code == 403
