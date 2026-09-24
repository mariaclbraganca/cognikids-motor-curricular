"""Text Mining em PT-BR — sem LLM (ADR-006).

Portado de `cognikids-adapt/notebooks/nucleo1_text_mining.ipynb`, já validado
com dado real: tabelas de verbos expandidas e reavaliadas contra os conjuntos
de teste em `notebooks/dados_avaliacao/` (100% de acurácia em Bloom's e
Simpson's após a correção da regra de desempate — ver ADR-006 no CLAUDE.md).
Não alterar as tabelas de verbos ou a lógica de classificação aqui sem
reavaliar contra esses conjuntos de teste.
"""

import re
import unicodedata

import pyphen

_dic_pt = pyphen.Pyphen(lang="pt_BR")


def _sem_acento(texto: str) -> str:
    """Remove acentuação, preservando o resto.

    As tabelas de verbos gravam as formas de imperativo SEM acento — por
    exemplo `reconheca` e `esclareca`, sem cedilha. O texto real do professor
    vem acentuado ("Reconheça as figuras"), e `\\b(reconheca)\\b` nunca casava
    com ele: eram verbos presentes na tabela que jamais disparavam, caindo no
    default BT1 em silêncio.

    Normalizar os dois lados corrige a classe inteira do problema de uma vez,
    em vez de acrescentar variante acentuada verbo a verbo.
    """
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def _contar_silabas_pt(palavra: str) -> int:
    return _dic_pt.inserted(palavra).count("-") + 1


def avaliar_complexidade_pt(texto: str) -> dict:
    """Índice Flesch adaptado para português (Martins et al. 1996, USP São Carlos)."""
    frases = [f for f in re.split(r"[.!?]+", texto) if f.strip()]
    palavras = re.findall(r"[A-Za-zÀ-ú]+", texto)

    if not frases or not palavras:
        return {"indice_flesch_pt": None, "contagem_palavras": 0}

    total_silabas = sum(_contar_silabas_pt(p) for p in palavras)
    asl = len(palavras) / len(frases)
    asw = total_silabas / len(palavras)
    indice = 248.835 - 1.015 * asl - 84.6 * asw

    return {
        "indice_flesch_pt": round(indice, 2),
        "contagem_palavras": len(palavras),
        "silabas_por_palavra": round(asw, 2),
    }


VERBOS_BLOOM_PT = {
    "BT1_lembrar": ["listar|liste|listem", "identificar|identifique|identifiquem",
                    "nomear|nomeie|nomeiem", "reconhecer|reconheca|reconhecam",
                    "definir|defina|definam", "citar|cite|citem",
                    "memorizar|memorize|memorizem", "descrever|descreva|descrevam",
                    "enumerar|enumere|enumerem", "apontar|aponte|apontem",
                    "assinalar|assinale|assinalem", "indicar|indique|indiquem"],
    "BT2_entender": ["explicar|explique|expliquem", "resumir|resuma|resumam",
                      "comparar|compare|comparem", "interpretar|interprete|interpretem",
                      "discutir|discuta|discutam", "exemplificar|exemplifique|exemplifiquem",
                      "classificar|classifique|classifiquem",
                      "esclarecer|esclareca|esclarecam", "reformular|reformule|reformulem"],
    "BT3_aplicar": ["resolver|resolva|resolvam", "usar|use|usem",
                     "aplicar|aplique|apliquem", "implementar|implemente|implementem",
                     "praticar|pratique|pratiquem", "demonstrar|demonstre|demonstrem",
                     "calcular|calcule|calculem",
                     "efetuar|efetue|efetuem", "realizar|realize|realizem", "executar|execute|executem"],
    "BT4_analisar": ["categorizar|categorize|categorizem", "investigar|investigue|investiguem",
                      "relacionar|relacione|relacionem", "examinar|examine|examinem",
                      "analisar|analise|analisem", "diferenciar|diferencie|diferenciem",
                      "distinguir|distinga|distingam", "confrontar|confronte|confrontem",
                      "decompor|decomponha|decomponham"],
    "BT5_avaliar": ["justificar|justifique|justifiquem", "argumentar|argumente|argumentem",
                     "criticar|critique|critiquem", "defender|defenda|defendam",
                     "avaliar|avalie|avaliem", "julgar|julgue|julguem",
                     "ponderar|pondere|ponderem", "validar|valide|validem"],
    "BT6_criar": ["criar|crie|criem", "gerar|gere|gerem",
                   "projetar|projete|projetem", "elaborar|elabore|elaborem",
                   "construir|construa|construam", "formular|formule|formulem",
                   "desenvolver|desenvolva|desenvolvam",
                   "inventar|invente|inventem", "conceber|conceba|concebam", "compor|componha|componham"],
}


def classificar_bloom_pt(texto: str) -> tuple:
    """Classifica intenção pedagógica (domínio cognitivo). Regra de desempate:
    entre níveis empatados no maior score, prevalece o nível cognitivo mais alto.
    """
    texto_lower = _sem_acento(texto.lower())
    pontuacao = {nivel: 0 for nivel in VERBOS_BLOOM_PT}
    for nivel, grupos_verbo in VERBOS_BLOOM_PT.items():
        for grupo in grupos_verbo:
            if re.search(rf"\b({_sem_acento(grupo)})\b", texto_lower):
                pontuacao[nivel] += 1

    maior_pontuacao = max(pontuacao.values())
    if maior_pontuacao == 0:
        return "BT1_lembrar (default)", pontuacao

    empatados = [nivel for nivel in VERBOS_BLOOM_PT if pontuacao[nivel] == maior_pontuacao]
    nivel_vencedor = empatados[-1]
    return nivel_vencedor, pontuacao


VERBOS_SIMPSON_PT = {
    "S1_percepcao":         ["observar|observe|observem", "perceber|perceba|percebam",
                              "detectar|detecte|detectem", "sentir|sinta|sintam",
                              "reparar|repare|reparem", "notar|note|notem"],
    "S2_prontidao":         ["preparar-se|prepare-se|preparem-se", "posicionar-se|posicione-se|posicionem-se",
                              "dispor-se|disponha-se|disponham-se"],
    "S3_resposta_guiada":   ["imitar|imite|imitem", "tentar|tente|tentem", "repetir|repita|repitam"],
    "S4_mecanismo":         ["montar|monte|montem", "manusear|maneje|manejem", "recortar|recorte|recortem",
                              "colar|cole|colem", "desenhar|desenhe|desenhem", "pintar|pinte|pintem",
                              "digitar|digite|digitem",
                              "encaixar|encaixe|encaixem", "dobrar|dobre|dobrem", "costurar|costure|costurem"],
    "S5_resposta_complexa": ["manobrar|manobre|manobrem", "coordenar|coordene|coordenem", "operar|opere|operem"],
    "S6_adaptacao":         ["ajustar|ajuste|ajustem", "adaptar|adapte|adaptem", "modificar|modifique|modifiquem"],
    "S7_criacao":           ["inventar|invente|inventem", "originar|origine|originem"],
}


def classificar_simpson_pt(texto: str) -> tuple:
    """Classifica demanda psicomotora (Simpson's Taxonomy, 1972). Sem verbo
    motor reconhecido, retorna None — diferente do Bloom's, aqui não há
    "default conservador" porque nem toda atividade tem componente motor.
    """
    texto_lower = _sem_acento(texto.lower())
    pontuacao = {nivel: 0 for nivel in VERBOS_SIMPSON_PT}
    for nivel, grupos_verbo in VERBOS_SIMPSON_PT.items():
        for grupo in grupos_verbo:
            if re.search(rf"\b({_sem_acento(grupo)})\b", texto_lower):
                pontuacao[nivel] += 1

    nivel_vencedor = max(pontuacao, key=pontuacao.get)
    if pontuacao[nivel_vencedor] == 0:
        return None, pontuacao
    return nivel_vencedor, pontuacao


def analisar_atividade(texto_professor: str) -> dict:
    """Combina complexidade + Bloom's (cognitivo) + Simpson's (psicomotor)."""
    nivel_bloom, pontuacao_bloom = classificar_bloom_pt(texto_professor)
    nivel_simpson, pontuacao_simpson = classificar_simpson_pt(texto_professor)

    return {
        "complexidade": avaliar_complexidade_pt(texto_professor),
        "intencao_pedagogica_bloom": nivel_bloom,
        "pontuacao_bloom_detalhe": pontuacao_bloom,
        "demanda_psicomotora_simpson": nivel_simpson,
        "pontuacao_simpson_detalhe": pontuacao_simpson,
    }
