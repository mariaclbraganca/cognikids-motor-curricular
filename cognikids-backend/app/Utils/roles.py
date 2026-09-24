"""
Perfis de usuario do CogniKids e normalizacao de tipos.

O sistema tem 3 perfis: professor, estudante e responsavel (pai).

Historicamente o banco recebeu variacoes para o mesmo perfil ('aluno',
'estudante', 'student'). O cadastro sempre gravou 'estudante', entao esse e o
valor canonico. As funcoes abaixo aceitam as variacoes na leitura para
compatibilidade com dados legados, mas a gravacao usa sempre o canonico.
"""

PROFESSOR = 'professor'
ESTUDANTE = 'estudante'
RESPONSAVEL = 'pai'
ADMIN = 'admin'

# Valor canonico -> variacoes aceitas na leitura (dados legados)
_ALIASES = {
    PROFESSOR: {'professor', 'teacher', 'docente'},
    ESTUDANTE: {'estudante', 'aluno', 'student'},
    RESPONSAVEL: {'pai', 'mae', 'responsavel', 'Responsavel', 'parent'},
    ADMIN: {'admin', 'administrador'},
}

# Indice reverso: variacao -> canonico
_CANONICO = {
    variacao: canonico
    for canonico, variacoes in _ALIASES.items()
    for variacao in variacoes
}

TIPOS_PERMITIDOS = [ESTUDANTE, PROFESSOR, RESPONSAVEL, ADMIN]

# Perfis que alguem pode criar para si mesmo em POST /api/register, que e
# uma rota publica (sem token). ADMIN fica deliberadamente de fora: e' um
# perfil que ignora consentimento em pode_ver_aluno/alunos_visiveis
# (authz.py), entao aceita-lo do corpo de uma requisicao anonima permitia
# que qualquer pessoa na internet lesse biometria, alertas e perfil
# funcional de todas as criancas da base. Admin agora so nasce pelo script
# scripts/criar_admin.py, que exige acesso ao servidor.
TIPOS_AUTOREGISTRAVEIS = [ESTUDANTE, PROFESSOR, RESPONSAVEL]

# Mapeamento para o front-end (mantido por compatibilidade com o dashboard)
ROLE_FRONTEND = {
    PROFESSOR: 'teacher',
    RESPONSAVEL: 'parent',
    ESTUDANTE: 'student',
    ADMIN: 'admin',
}


def normalizar_tipo(tipo):
    """Converte qualquer variacao para o valor canonico.

    Retorna None se o tipo nao for reconhecido.
    """
    if not tipo:
        return None
    return _CANONICO.get(str(tipo).strip().lower())


def variacoes_de(tipo_canonico):
    """Variacoes aceitas de um perfil, para uso em queries com $in.

    Necessario porque documentos antigos podem ter 'aluno' ou 'student'
    gravados no campo 'tipo'.
    """
    return sorted(_ALIASES.get(tipo_canonico, {tipo_canonico}))


def eh(user, *tipos_canonicos):
    """Verifica se o usuario pertence a algum dos perfis informados."""
    if not user:
        return False
    atual = normalizar_tipo(user.get('tipo'))
    return atual in tipos_canonicos


def eh_professor(user):
    return eh(user, PROFESSOR)


def eh_estudante(user):
    return eh(user, ESTUDANTE)


def eh_responsavel(user):
    return eh(user, RESPONSAVEL)


def eh_admin(user):
    return eh(user, ADMIN)
