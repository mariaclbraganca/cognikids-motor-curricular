# app/models/support_kit_model.py
from bson.objectid import ObjectId
import datetime

class SupportKitModel:
    """
    Define a estrutura para o Kit de Apoio de um aluno.
    """
    @staticmethod
    def get_schema(aluno_id, updated_by_id):
        # Nao existe campo de diagnostico aqui, e isso e deliberado. O campo
        # "neurodivergencia" (texto livre) existia e foi removido: guardava
        # dado sensivel de saude de menor (LGPD art. 11 c/c art. 14) e
        # contradizia frontalmente a ADR-003 e o cabecalho de
        # app/Utils/accessibility.py, que afirmam que o sistema nao pergunta
        # nem armazena diagnostico. Agravante: o proprio aluno conseguia le-lo,
        # porque pode_ver_aluno libera o proprio usuario (authz.py) e a rota
        # GET /api/support-kit/<id> so exige essa checagem.
        # Nenhuma logica de negocio consumia o campo — a remocao nao tem perda
        # funcional. O que orienta a resposta a uma crise sao os campos abaixo,
        # todos observaveis e acionaveis.
        return {
            "aluno_id": ObjectId(aluno_id),
            "interesses": [], # Lista de strings, ex: ["Desenho", "Dinossauros"]
            "sensibilidades": [], # Lista de strings, ex: ["Ruídos altos", "Luzes fortes"]
            "estrategias_calmantes": "", # Campo de texto livre
            "contatos_emergencia": [
                # { "nome": "...", "relacao": "...", "telefone": "..." }
            ],
            "last_updated": datetime.datetime.utcnow(),
            "updated_by": ObjectId(updated_by_id) # ID do pai/responsável
        }