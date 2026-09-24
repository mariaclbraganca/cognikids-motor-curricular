"""
Fronteiras de autorizacao entre os 3 perfis.

Cada teste aqui corresponde a um acesso que a versao anterior permitia
indevidamente. Os dados sao biometricos e de menores neurodivergentes, logo
o vazamento entre turmas e o risco mais serio do sistema.
"""

import pytest
from bson.objectid import ObjectId


class TestIsolamentoEntreProfessores:
    """IDOR: professor B nao pode tocar nos dados da turma do professor A."""

    def test_nao_le_turma_alheia(self, outro_professor, turma):
        assert outro_professor.get(f'/api/classes/{turma}').status_code == 403

    def test_nao_edita_turma_alheia(self, outro_professor, turma, db):
        r = outro_professor.put(f'/api/classes/{turma}', json={'name': 'INVADIDA'})
        assert r.status_code == 403
        assert db.turmas.find_one({'_id': turma})['name'] == 'Turma Teste'

    def test_nao_edita_turma_alheia_pela_rota_legada(self, outro_professor, turma, db):
        r = outro_professor.put(f'/api/classes/classes/{turma}', json={'name': 'INVADIDA'})
        assert r.status_code == 403
        assert db.turmas.find_one({'_id': turma})['name'] == 'Turma Teste'

    def test_nao_desativa_turma_alheia(self, outro_professor, turma, db):
        r = outro_professor.delete(f'/api/classes/{turma}')
        assert r.status_code == 403
        assert db.turmas.find_one({'_id': turma}).get('is_active') is True

    def test_nao_matricula_aluno_em_turma_alheia(self, outro_professor, turma, criar_usuario):
        novo = criar_usuario('estudante')
        r = outro_professor.post(f'/api/classes/{turma}/enroll_student',
                                 json={'student_id': novo.id})
        assert r.status_code == 403

    def test_nao_remove_aluno_de_turma_alheia(self, outro_professor, turma, estudante):
        r = outro_professor.post(f'/api/classes/{turma}/remove_student',
                                 json={'student_id': estudante.id})
        assert r.status_code == 403

    def test_nao_edita_aluno_alheio(self, outro_professor, turma, estudante, db):
        r = outro_professor.put(f'/api/students/{estudante.id}', json={'nome': 'Alterado'})
        assert r.status_code == 403
        assert db.users.find_one({'_id': estudante.oid})['nome'] != 'Alterado'

    def test_nao_remove_aluno_alheio(self, outro_professor, turma, estudante, db):
        r = outro_professor.delete(f'/api/students/{estudante.id}')
        assert r.status_code == 403
        assert db.users.find_one({'_id': estudante.oid}) is not None

    def test_nao_le_sentimentos_de_aluno_alheio(self, outro_professor, turma, estudante):
        r = outro_professor.get(f'/api/teachers/students/{estudante.id}/feelings')
        assert r.status_code == 403

    def test_nao_le_metas_de_aluno_alheio(self, outro_professor, turma, estudante):
        assert outro_professor.get(f'/api/students/{estudante.id}/goals').status_code == 403

    def test_nao_le_kit_de_apoio_de_aluno_alheio(self, outro_professor, turma,
                                                 estudante, db):
        """O kit reune os dados mais sensiveis do aluno."""
        db.support_kits.insert_one({
            'aluno_id': estudante.oid, 'sensibilidades': ['ruido alto'],
            'estrategias_calmantes': 'ambiente silencioso',
        })
        r = outro_professor.get(f'/api/support-kit/{estudante.id}')
        assert r.status_code == 403

    def test_feelings_all_so_traz_alunos_proprios(self, outro_professor, turma,
                                                  estudante, db):
        """Antes devolvia os sentimentos de toda a base."""
        db.feelings.insert_one({
            'aluno_id': estudante.oid, 'sentimento': 'triste', 'emoji': 'x',
        })
        r = outro_professor.get('/api/teachers/feelings/all')
        assert r.status_code == 200
        assert r.get_json()['data'] == []

    def test_professor_titular_mantem_acesso(self, professor, turma):
        """A restricao nao pode quebrar o caso legitimo."""
        assert professor.get(f'/api/classes/{turma}').status_code == 200

    def test_nao_ve_alunos_de_outro_professor(self, outro_professor, turma):
        r = outro_professor.get('/api/teachers/all_students')
        assert r.status_code == 200
        assert r.get_json()['data'] == []


class TestIsolamentoEntreResponsaveis:
    def test_responsavel_nao_ve_filho_alheio(self, responsavel, estudante):
        assert responsavel.get(
            f'/api/parents/children/{estudante.id}/feelings').status_code == 403

    def test_responsavel_nao_edita_kit_de_aluno_alheio(self, responsavel, estudante):
        r = responsavel.put(f'/api/support-kit/{estudante.id}',
                            json={'estrategias_calmantes': 'invasao'})
        assert r.status_code == 403

    def test_responsavel_vinculado_acessa_o_filho(self, vinculo_responsavel, estudante):
        assert vinculo_responsavel.get(
            f'/api/parents/children/{estudante.id}/feelings').status_code == 200

    def test_responsavel_so_lista_os_proprios_filhos(self, vinculo_responsavel,
                                                     criar_usuario):
        criar_usuario('estudante')  # aluno de outra familia
        r = vinculo_responsavel.get('/api/parents/children')
        assert r.get_json()['total'] == 1


class TestIsolamentoEntreEstudantes:
    def test_estudante_nao_le_metas_de_outro(self, estudante, criar_usuario):
        outro = criar_usuario('estudante')
        assert outro.get(f'/api/students/{estudante.id}/goals').status_code == 403

    def test_estudante_le_as_proprias_metas(self, estudante):
        assert estudante.get(f'/api/students/{estudante.id}/goals').status_code == 200

    def test_estudante_nao_cria_turma(self, estudante):
        assert estudante.post('/api/classes', json={'name': 'X'}).status_code == 403

    def test_estudante_nao_cria_aluno(self, estudante, turma):
        r = estudante.post('/api/students', json={
            'nome': 'X', 'email': 'x@x.com', 'senha': 'senha123', 'turma_id': str(turma),
        })
        assert r.status_code == 403

    def test_estudante_nao_acessa_dashboard_do_professor(self, estudante):
        assert estudante.get('/api/teachers/all_students').status_code == 403

    def test_estudante_nao_lanca_notas(self, estudante):
        r = estudante.post('/api/grades/grades', json={
            'assignment_id': str(ObjectId()), 'student_id': estudante.id, 'score': 10,
        })
        assert r.status_code == 403


class TestSeparacaoDePerfis:
    @pytest.mark.parametrize('rota', [
        '/api/teachers/all_students',
        '/api/teachers/crisis_alerts',
        '/api/teachers/dashboard',
        '/api/teachers/feelings/all',
    ])
    def test_rotas_de_professor_negam_responsavel(self, responsavel, rota):
        assert responsavel.get(rota).status_code == 403

    @pytest.mark.parametrize('rota', [
        '/api/parents/children',
        '/api/parents/dashboard',
    ])
    def test_rotas_de_responsavel_negam_professor(self, professor, rota):
        assert professor.get(rota).status_code == 403

    def test_rota_de_aluno_nega_professor(self, professor):
        r = professor.post('/api/students/feelings',
                           json={'sentimento': 'feliz', 'emoji': 'x'})
        assert r.status_code == 403

    def test_responsavel_nao_cria_desafio(self, responsavel):
        r = responsavel.post('/api/challenges',
                             json={'title': 'X', 'description': 'Y'})
        assert r.status_code == 403


class TestValidacaoDeEntrada:
    @pytest.mark.parametrize('rota', [
        '/api/students/id-invalido/goals',
        '/api/iot/registros/id-invalido',
        '/api/support-kit/id-invalido',
    ])
    def test_id_malformado_retorna_400(self, professor, rota):
        assert professor.get(rota).status_code == 400

    def test_recurso_inexistente_retorna_404(self, professor):
        r = professor.get(f'/api/classes/{ObjectId()}')
        assert r.status_code == 404

    def test_erro_nao_vaza_stack_trace(self, professor):
        """Nenhuma resposta deve conter detalhes internos."""
        r = professor.get(f'/api/classes/{ObjectId()}')
        corpo = r.get_data(as_text=True).lower()
        assert 'traceback' not in corpo
        assert 'mongo' not in corpo
