"""Testes de autorizacao do job de adaptacao — tentam o acesso indevido.

GET /v1/curriculum/jobs/{job_id} exigia apenas um JWT valido de qualquer
perfil, sem nenhuma checagem de propriedade (IDOR). Quem obtivesse um
job_id — de um log, de uma URL, do proprio app — lia o conteudo original da
atividade, a lista de alunos e, quando o worker de adaptacao existir,
`profile_tokens_used`, que e o perfil funcional da crianca.
"""

from app.services.curriculum_service import pode_ver_job

JOB = {
    "job_id": "job-1",
    "teacher_id": "prof-dono",
    "student_ids": ["aluno-a", "aluno-b"],
}


def test_professor_dono_ve_o_proprio_job():
    assert pode_ver_job(JOB, {"user_id": "prof-dono", "role": "professor"}) is True


def test_aluno_citado_ve_o_job():
    """O aluno precisa ler o job para receber a atividade adaptada dele."""
    assert pode_ver_job(JOB, {"user_id": "aluno-b", "role": "estudante"}) is True


def test_outro_professor_nao_ve_o_job():
    assert pode_ver_job(JOB, {"user_id": "prof-alheio", "role": "professor"}) is False


def test_aluno_de_fora_nao_ve_o_job():
    assert pode_ver_job(JOB, {"user_id": "aluno-z", "role": "estudante"}) is False


def test_responsavel_ainda_nao_tem_acesso():
    """Negar por padrao enquanto a checagem de filiacao no core nao existe.

    Liberar o responsavel exige perguntar ao core se aquele aluno e filho
    dele. Ate isso existir, o lado seguro e recusar — este teste falha no
    dia em que alguem liberar sem implementar a checagem.
    """
    assert pode_ver_job(JOB, {"user_id": "pai-do-aluno-a", "role": "pai"}) is False


def test_job_sem_alunos_so_e_visto_pelo_dono():
    job = {"job_id": "job-2", "teacher_id": "prof-dono"}
    assert pode_ver_job(job, {"user_id": "prof-dono", "role": "professor"}) is True
    assert pode_ver_job(job, {"user_id": "qualquer", "role": "estudante"}) is False
