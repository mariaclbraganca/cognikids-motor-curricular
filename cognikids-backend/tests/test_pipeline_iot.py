"""
Pipeline IoT -> ML -> dashboard.

Estes testes cobrem o defeito central que impedia a PoC de funcionar: o
alert_monitor gravava alertas com a chave 'aluno_id' enquanto o dashboard
consultava 'student_id', de modo que nenhuma crise detectada pelo modelo
chegava ao professor.
"""

import datetime

import pytest
from bson.objectid import ObjectId


class TestIngestaoIoT:
    def test_rejeita_sem_api_key(self, client, dispositivo):
        r = client.post('/api/iot/data', json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 90},
        })
        assert r.status_code == 401

    def test_rejeita_api_key_errada(self, client, dispositivo):
        r = client.post('/api/iot/data',
                        headers={'X-API-Key': 'chave-errada'},
                        json={'dispositivo_id': str(dispositivo),
                              'dados_biometricos': {'bpm': 90}})
        assert r.status_code == 401

    def test_aceita_leitura_valida(self, client, api_key_headers, dispositivo, db):
        r = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 92, 'gsr': 1.2, 'movement_score': 0.8},
        })
        assert r.status_code == 201
        assert db.registros_iot.count_documents({}) == 1

    def test_grava_em_registros_iot_com_aluno_id(self, client, api_key_headers,
                                                 dispositivo, estudante, db):
        """A colecao e o nome do campo precisam bater com o que a API le."""
        client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 92},
        })
        registro = db.registros_iot.find_one()
        assert registro['aluno_id'] == estudante.oid

    def test_normaliza_heart_rate_para_bpm(self, client, api_key_headers, dispositivo, db):
        client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'heart_rate': 130, 'eda': 3.2},
        })
        bio = db.registros_iot.find_one()['dados_biometricos']
        assert bio['bpm'] == 130
        assert bio['gsr'] == 3.2

    def test_rejeita_dispositivo_inexistente(self, client, api_key_headers):
        r = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(ObjectId()),
            'dados_biometricos': {'bpm': 90},
        })
        assert r.status_code == 404

    def test_rejeita_id_malformado(self, client, api_key_headers):
        r = client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': 'nao-e-objectid',
            'dados_biometricos': {'bpm': 90},
        })
        assert r.status_code == 400

    def test_atualiza_ultima_conexao(self, client, api_key_headers, dispositivo, db):
        client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 90},
        })
        assert db.dispositivos.find_one({'_id': dispositivo})['ultima_conexao']


class TestAlertasChegamAoDashboard:
    """Regressao do bug aluno_id vs student_id."""

    def test_professor_ve_alerta_do_ml_em_crisis_alerts(self, professor, turma, alerta):
        r = professor.get('/api/teachers/crisis_alerts')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1

    def test_professor_ve_alerta_em_iot_crisis_alerts(self, professor, turma, alerta):
        """Esta rota retornava 401 por usar uma chave JWT diferente."""
        r = professor.get('/api/iot/crisis-alerts')
        assert r.status_code == 200
        assert r.get_json()['count'] == 1

    def test_alerta_aparece_no_historico(self, professor, turma, estudante, alerta):
        r = professor.get(f'/api/teachers/students/{estudante.id}/alerts_history')
        assert r.status_code == 200
        assert r.get_json()['data']['total_alertas'] == 1

    def test_os_dois_endpoints_de_historico_concordam(self, professor, turma,
                                                      estudante, alerta):
        """Antes um lia 'aluno_id' e o outro 'student_id', divergindo."""
        a = professor.get(f'/api/teachers/students/{estudante.id}/alerts_history')
        b = professor.get(f'/api/teachers/students/{estudante.id}/alert_history')
        assert a.get_json()['data']['total_alertas'] == b.get_json()['count'] == 1

    def test_dados_biometricos_preservados(self, professor, turma, estudante, alerta):
        r = professor.get(f'/api/teachers/students/{estudante.id}/alerts_history')
        registro = r.get_json()['data']['historico'][0]
        assert registro['bpm'] == 155
        assert registro['gsr'] == 4.8
        assert registro['severity'] == 'high'

    def test_responsavel_ve_alertas_do_filho(self, vinculo_responsavel, estudante, alerta):
        r = vinculo_responsavel.get(f'/api/parents/children/{estudante.id}/alerts')
        assert r.status_code == 200
        assert r.get_json()['count'] == 1

    def test_resolver_alerta(self, professor, turma, alerta, db):
        r = professor.put(f'/api/iot/alerts/{alerta}/resolve')
        assert r.status_code == 200
        assert db.alerts.find_one({'_id': alerta})['resolvido'] is True

    def test_alerta_antigo_fora_da_janela_nao_aparece(self, professor, turma, estudante, db):
        db.alerts.insert_one({
            'aluno_id': estudante.oid,
            'data_hora': datetime.datetime.utcnow() - datetime.timedelta(days=2),
            'dados_biometricos': {'bpm': 150},
            'severity': 'high',
        })
        assert professor.get('/api/teachers/crisis_alerts').get_json()['data'] == []


class TestIsolamentoDeAlertas:
    def test_professor_sem_vinculo_nao_ve_alerta(self, outro_professor, turma, alerta):
        r = outro_professor.get('/api/teachers/crisis_alerts')
        assert r.status_code == 200
        assert r.get_json()['data'] == []

    def test_professor_sem_vinculo_nao_le_historico(self, outro_professor, turma,
                                                    estudante, alerta):
        """IDOR: antes retornava 200 com o historico biometrico completo."""
        r = outro_professor.get(f'/api/teachers/students/{estudante.id}/alerts_history')
        assert r.status_code == 403

    def test_responsavel_nao_ve_alerta_de_aluno_alheio(self, responsavel, estudante, alerta):
        r = responsavel.get(f'/api/parents/children/{estudante.id}/alerts')
        assert r.status_code == 403

    def test_estudante_nao_acessa_registros_de_outro(self, estudante, criar_usuario,
                                                     dispositivo):
        outro = criar_usuario('estudante')
        r = outro.get(f'/api/iot/registros/{estudante.id}')
        assert r.status_code == 403


class TestConsultaDeRegistros:
    def test_professor_lista_registros_do_aluno(self, client, api_key_headers, professor,
                                                turma, estudante, dispositivo):
        client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 88},
        })
        r = professor.get(f'/api/iot/registros/{estudante.id}')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1

    def test_estudante_ve_os_proprios_registros(self, client, api_key_headers,
                                                estudante, dispositivo):
        client.post('/api/iot/data', headers=api_key_headers, json={
            'dispositivo_id': str(dispositivo),
            'dados_biometricos': {'bpm': 88},
        })
        assert estudante.get(f'/api/iot/registros/{estudante.id}').status_code == 200

    def test_professor_lista_dispositivos(self, professor, turma, estudante, dispositivo):
        r = professor.get(f'/api/iot/dispositivos/{estudante.id}')
        assert r.status_code == 200
        assert len(r.get_json()['data']) == 1


@pytest.fixture
def ponte():
    """Modulo da ponte MQTT.

    So e importavel sem Mongo/Redis no ar porque as conexoes ficam em
    conectar(), e nao no corpo do modulo.
    """
    pytest.importorskip('paho.mqtt.client')
    import mqtt_to_redis_bridge

    return mqtt_to_redis_bridge


class TestTransformacaoDaPulseira:
    """A ponte MQTT nao pode confundir zero com ausencia de leitura."""

    def test_movimento_zero_e_preservado(self, ponte):
        """mov=0 significa aluno imovel — sinal clinico, nao ausencia."""
        out = ponte.transformar_payload_pulseira(
            {'id': 'x', 'bpm': 80, 'mov': 0, 'ts': 1700000000}
        )
        assert out['dados_biometricos']['movement_score'] == 0

    def test_bateria_zero_e_preservada(self, ponte):
        out = ponte.transformar_payload_pulseira(
            {'id': 'x', 'bpm': 80, 'batt': 0, 'ts': 1700000000}
        )
        assert out['bateria'] == 0

    def test_gsr_ausente_vira_none_e_nao_zero(self, ponte):
        """Zero e um valor valido de GSR; ausencia precisa ser distinguivel."""
        out = ponte.transformar_payload_pulseira(
            {'id': 'x', 'bpm': 80, 'ts': 1700000000}
        )
        assert out['dados_biometricos']['gsr'] is None

    def test_aceita_o_formato_completo(self, ponte):
        out = ponte.transformar_payload_pulseira({
            'device_id': 'y', 'bpm': 95, 'movement': 1.5, 'timestamp': 1700000000,
        })
        assert out['dispositivo_id'] == 'y'
        assert out['dados_biometricos']['movement_score'] == 1.5

    def test_primeiro_valido_preserva_zero(self, ponte):
        """`or` devolveria 5 aqui; a leitura zero seria descartada."""
        assert ponte._primeiro_valido(0, 5) == 0
        assert ponte._primeiro_valido(None, 5) == 5
        assert ponte._primeiro_valido(None, None) is None


class TestInferenciaDoConsumidor:
    """Classificacao de severidade usada pelo alert_monitor."""

    @pytest.fixture
    def consumidor(self):
        # alert_monitor importa pandas/joblib; se o ambiente nao os tiver
        # disponiveis, estes testes sao pulados em vez de falharem.
        pytest.importorskip('pandas')
        pytest.importorskip('joblib')
        import alert_monitor

        return alert_monitor

    def test_bpm_alto_classifica_como_high(self, consumidor):
        assert consumidor.classificar_severidade({'bpm': 160, 'gsr': 1.0}) == 'high'

    def test_gsr_alto_classifica_como_high(self, consumidor):
        assert consumidor.classificar_severidade({'bpm': 90, 'gsr': 5.0}) == 'high'

    def test_valores_moderados_classificam_como_medium(self, consumidor):
        assert consumidor.classificar_severidade({'bpm': 100, 'gsr': 2.0}) == 'medium'

    def test_severidade_coincide_com_a_do_modelo_de_alertas(self, consumidor):
        """Consumidor e API precisam concordar sobre o que e uma crise grave."""
        from app.Models.alert_model import classificar_severidade as da_api

        for dados in ({'bpm': 160, 'gsr': 1.0}, {'bpm': 90, 'gsr': 5.0},
                      {'bpm': 100, 'gsr': 2.0}):
            assert consumidor.classificar_severidade(dados) == da_api(dados)

    def test_limiares_sao_os_mesmos_dos_dois_lados(self, consumidor):
        """Os limiares tambem precisam ser o MESMO valor, nao so concordar
        nos poucos casos testados acima — um `LIMIAR_BPM_ALTO` diferente em
        cada arquivo passaria nos testes de caso e ainda assim divergiria
        num valor de fronteira nao coberto.
        """
        from app.Models import alert_model

        assert consumidor.LIMIAR_BPM_ALTO == alert_model.LIMIAR_BPM_ALTO
        assert consumidor.LIMIAR_GSR_ALTO == alert_model.LIMIAR_GSR_ALTO


class TestModeloRiscoNaoValidado:
    """ADR-010: nenhum uso com crianca real ate o modelo ser validado.

    modelo_validado grava esse estado em CADA alerta, em vez de deixar so
    documentado em comentario — para a UI poder avisar quem le.
    """

    def test_create_alert_grava_modelo_validado_false_por_padrao(self, app, estudante, db):
        from app.Models.alert_model import Alert

        Alert().create_alert({
            'aluno_id': str(estudante.oid),
            'dados_biometricos': {'bpm': 160, 'gsr': 1.0},
        })

        assert db.alerts.find_one({'aluno_id': estudante.oid})['modelo_validado'] is False

    def test_serializar_e_seguro_para_alerta_antigo_sem_o_campo(self):
        from app.Models.alert_model import Alert

        alerta_antigo = {
            'aluno_id': ObjectId(),
            'dados_biometricos': {'bpm': 160},
            'severity': 'high',
            # sem 'modelo_validado' — formato anterior a esta correcao
        }
        assert Alert.serializar(alerta_antigo)['modelo_validado'] is False

    def test_professor_ve_modelo_validado_no_alerta_de_crise(self, professor, turma, alerta):
        r = professor.get('/api/teachers/crisis_alerts')
        assert r.get_json()['data'][0]['modelo_validado'] is False

    def test_consumidor_mantem_a_mesma_flag_do_modelo_de_alertas(self, consumidor):
        from app.Models import alert_model

        assert consumidor.MODELO_VALIDADO == alert_model.MODELO_VALIDADO

    @pytest.fixture
    def consumidor(self):
        pytest.importorskip('pandas')
        pytest.importorskip('joblib')
        import alert_monitor

        return alert_monitor
