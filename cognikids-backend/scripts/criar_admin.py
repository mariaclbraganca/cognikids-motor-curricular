"""Cria um usuario admin. Unico caminho para isso desde a correcao de seguranca.

POST /api/register e uma rota publica e passou a recusar tipo='admin'
(ver Utils/roles.py, TIPOS_AUTOREGISTRAVEIS). Antes disso, qualquer pessoa
com acesso de rede a API criava um admin para si — e admin ignora
consentimento em pode_ver_aluno e alunos_visiveis (Utils/authz.py), o que
liberava biometria, alertas e perfil funcional de todas as criancas.

Rodar este script exige acesso ao servidor e ao .env com a MONGO_URI, que e
a barreira que a rota HTTP nao tinha.

Uso:
    cd cognikids-backend
    python scripts/criar_admin.py --nome "Servico Satelite" \
        --email satelite-service@cognikids.internal

A senha e pedida no terminal (nao vai por argumento, para nao ficar no
historico do shell). O ObjectId impresso no fim e o valor de
CORE_SERVICE_USER_ID no .env da raiz.
"""

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import bcrypt, create_app  # noqa: E402
from app.Models.user_model import User  # noqa: E402
from app.Utils.roles import ADMIN  # noqa: E402
from app.Utils.validators import validate_email  # noqa: E402

SENHA_MIN_LEN = 12


def main():
    parser = argparse.ArgumentParser(description='Cria um usuario admin no core.')
    parser.add_argument('--nome', required=True, help='Nome do usuario admin')
    parser.add_argument('--email', required=True, help='E-mail do usuario admin')
    args = parser.parse_args()

    email = args.email.strip().lower()
    if not validate_email(email):
        parser.error(f'E-mail invalido: {email}')

    # Minimo maior que o da rota publica (6): uma conta que ignora
    # consentimento nao deve aceitar senha curta.
    senha = getpass.getpass(f'Senha do admin (min. {SENHA_MIN_LEN} caracteres): ')
    if len(senha) < SENHA_MIN_LEN:
        parser.error(f'A senha deve ter pelo menos {SENHA_MIN_LEN} caracteres')
    if senha != getpass.getpass('Confirme a senha: '):
        parser.error('As senhas nao conferem')

    app = create_app()
    with app.app_context():
        user_model = User()

        if user_model.find_user_by_email(email):
            print(f'ERRO: ja existe usuario com o e-mail {email}', file=sys.stderr)
            return 1

        resultado = user_model.create_user({
            'nome': args.nome.strip(),
            'email': email,
            'senha': bcrypt.generate_password_hash(senha).decode('utf-8'),
            'tipo': ADMIN,
            'turma_id': None,
        })

        if not resultado.get('success'):
            print(f'ERRO: {resultado.get("message")}', file=sys.stderr)
            return 1

        user_id = resultado.get('user_id')
        print(f'\nAdmin criado: {email}')
        print(f'ObjectId: {user_id}')
        print('\nSe este for o usuario de servico do satelite, use no .env da raiz:')
        print(f'CORE_SERVICE_USER_ID={user_id}')
        return 0


if __name__ == '__main__':
    sys.exit(main())
