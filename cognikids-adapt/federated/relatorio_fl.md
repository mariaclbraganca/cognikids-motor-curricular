# Relatório — Experimento Federated Learning (Sprint 3)

## Metodologia

Comparação de duas formas de treinar o mesmo classificador de risco de
crise (`SGDClassifier`, `loss="log_loss"` — equivalente a regressão
logística treinada por gradiente estocástico, sobre as features BPM/GSR/
movimento) em 4 escolas simuladas com proporções diferentes de perfil
"ansioso" (10.8% a 39.2% de taxa de crise — não-IID de propósito, ver
`fl_dataset.py`):

1. **Centralizado**: todo o dado das 4 escolas é agrupado antes do treino —
   representa o "melhor caso possível" de acurácia, mas que nenhuma escola
   aceitaria na prática, já que envolveria dado biométrico sensível de
   criança saindo da instituição (ver ADR-003/004 no CLAUDE.md).
2. **Federado (FedAvg via Flower)**: cada escola treina localmente por 1
   época a cada rodada; só os parâmetros do modelo (`coef_`/`intercept_`,
   nunca o dado bruto) trafegam e são agregados pela função `aggregate()`
   real do Flower (`flwr.server.strategy.aggregate`) — média ponderada pelo
   número de amostras de cada escola, a mesma lógica usada internamente
   pela estratégia `FedAvg` do framework.

Os dois cenários usam o mesmo otimizador (SGD) e o mesmo número total de
épocas (15), para isolar o efeito específico de "acesso centralizado ao
dado de uma vez" vs. "treino distribuído com agregação" — não é uma
comparação entre otimizadores diferentes.

Avaliação em um conjunto de teste global (600 amostras, 150 por escola,
seeds diferentes das usadas no treino) — a mesma distribuição mista pros
dois modelos, pra comparação justa.

**Execução manual das rodadas, não o simulador do Flower.** O simulador
oficial (`flwr.simulation.run_simulation`) depende do Ray, que tem suporte
instável no Windows — o loop de rodadas foi conduzido diretamente aqui,
mas usando os componentes reais do Flower (`NumPyClient`, `aggregate()`),
não uma reimplementação própria do FedAvg.

## Resultados

| Cenário | Acurácia no teste global |
|---|---|
| Centralizado (15 épocas sobre o dado agrupado) | **0,747** |
| Federado (FedAvg, 15 rodadas, 1 época local/rodada) | **0,747** |

**Diferença: 0,000 — os dois empataram.**

Acurácia local média por rodada (federado) variou entre 0,761 e 0,788,
majoritariamente estável em 0,764 — evidência de que o modelo converge
cedo e as rodadas adicionais têm pouco efeito adicional nesse cenário
(dataset relativamente simples, fronteira de decisão quase linear).

## Interpretação

O resultado confirma, com número real e reproduzível (determinístico por
seed), a motivação da ADR-004: é possível treinar um classificador
federado sem nenhuma escola expor seus dados brutos, **sem perda de
acurácia** em relação ao treino centralizado neste cenário. Isso é
esperado para um modelo linear (SGD/regressão logística) sobre um problema
com fronteira de decisão relativamente simples — FedAvg tende a se
aproximar mais do centralizado quanto mais convexo/linear for o modelo,
diferente do que aconteceria com um modelo muito mais expressivo (ex.
Random Forest, que nem é diretamente compatível com FedAvg, pois não tem
parâmetros contínuos para agregar por média).

## Limitações

- **Dataset sintético**, sem dado real de criança (mesma regra do resto
  do projeto — ADR-003). Os números de acurácia não devem ser lidos como
  desempenho esperado em produção, só como validação de que o mecanismo
  de FedAvg funciona e não degrada em relação ao centralizado.
- **Não-IID moderado** (10,8% a 39,2% de taxa de crise entre escolas) —
  um cenário com desbalanceamento mais extremo entre escolas poderia
  mostrar uma diferença maior entre federado e centralizado; não foi
  testado aqui.
- **Simulador do Flower não usado** (rodadas conduzidas manualmente, ver
  Metodologia) — em produção real, com escolas em redes/latências
  diferentes, o comportamento operacional (não a matemática do FedAvg)
  precisaria ser validado com o simulador ou um deployment real.
- **Learning rate `"optimal"` do `SGDClassifier`** decai com o número
  total de passos de gradiente já executados por cada cliente — isso
  pode ter contribuído para a acurácia local estabilizar cedo (poucas
  mudanças após a rodada ~5); não foi comparado com um learning rate
  fixo.

## Reprodutibilidade

```bash
cd cognikids-adapt/federated
pip install -r requirements.txt
python experimento_fedavg.py --rounds 15
pytest tests/  # 8 testes: geração de dados + parâmetros do modelo
```
