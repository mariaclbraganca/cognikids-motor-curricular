import pytest

from app.services.curriculum_service import _estimar_segundos


@pytest.mark.parametrize(
    "quantidade_alunos,esperado",
    [
        (0, 5),
        (1, 7),
        (3, 11),
        (30, 65),
    ],
)
def test_estimar_segundos_cresce_com_a_quantidade_de_alunos(quantidade_alunos, esperado):
    assert _estimar_segundos(quantidade_alunos) == esperado
