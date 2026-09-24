<div align="center">

# CogniKids, Motor de Adaptação Curricular

**Fase 2 do CogniKids — IA para personalização de atividades escolares para crianças neurodivergentes**

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![scikit-learn](https://img.shields.io/badge/scikit--learn-F7931E?style=for-the-badge&logo=scikit-learn&logoColor=white)
![PySpark](https://img.shields.io/badge/Apache_Spark-E25A1C?style=for-the-badge&logo=apachespark&logoColor=white)
![Status](https://img.shields.io/badge/Status-Em%20desenvolvimento-blue?style=for-the-badge)

</div>

---

Este repositório dá continuidade ao [CogniKids Fase 1](https://github.com/mariaclbraganca/cognikids), que detectava crises de desregulação emocional em crianças neurodivergentes em tempo real. A Fase 1 foi concluída como prova de conceito e reconhecida com 3º Melhor Artigo no SBCUP 2026. Ela está em pausa aguardando aprovação dos órgãos reguladores para validação com crianças reais.

O Motor de Adaptação Curricular é desenvolvido em paralelo enquanto esse processo acontece. O problema que ele resolve é diferente do da Fase 1: a Fase 1 detecta o estado emocional da criança, mas não mexe na atividade. O motor resolve a pergunta seguinte: dado que sabemos que a criança tem dislexia e está com risco de frustração crescente, o que mudamos na atividade para que ela consiga concluir sem abandonar? O conteúdo pedagógico nunca muda, só a forma de apresentar.

---

## Como o motor funciona

O motor precisa responder a três perguntas antes de adaptar qualquer coisa:

**1. O que o texto da atividade está pedindo?**
Antes de adaptar, o sistema precisa entender a complexidade do texto e a intenção pedagógica do professor: ele quer que o aluno memorize, explique, analise ou crie? Isso importa porque uma adaptação que simplifica demais pode trocar, sem querer, um objetivo de análise por um de memorização. Essa parte é resolvida no Núcleo 1.

**2. O que esse aluno já sabe?**
A adaptação precisa partir do que a criança já domina, não do zero. O Núcleo 2 constrói um Grafo de Conhecimento do aluno com arestas ponderadas por taxa de acerto, latência e persistência, calibrado com dados públicos de comportamento real (ASSISTments 2009 e EdNet) antes de existir qualquer dado de uso real do sistema.

**3. Esse aluno está em risco de frustração agora?**
Adaptar a atividade depois que a criança já abandonou a tarefa é tarde demais. O Núcleo 3 prevê o risco de frustração e fadiga a partir do histórico recente de tentativas, processado com Spark, para que a adaptação aconteça antes do desengajamento.

---

## Estrutura dos notebooks

| Núcleo | Arquivo | O que resolve | Tecnologias |
|--------|---------|---------------|-------------|
| 1 | [`nucleo1_text_mining.ipynb`](./nucleo1_text_mining.ipynb) | Extrai complexidade textual (CLEAR Corpus), intenção pedagógica (Taxonomia de Bloom) e demanda psicomotora (Taxonomia de Simpson) do texto da atividade, sem depender de modelo pesado ou serviço externo | `textstat` `pyphen` `TF-IDF` `LightGBM` `SVC` |
| 2 | [`nucleo2_grafo_conhecimento.ipynb`](./nucleo2_grafo_conhecimento.ipynb) | Constrói o Grafo de Conhecimento do aluno com pesos calibrados por dados públicos reais. O ASSISTments oferece sinal de acerto e persistência; o EdNet oferece latência e abandono | `NetworkX` `pandas` `scipy` |
| 3 | [`nucleo3_risco_frustracao.ipynb`](./nucleo3_risco_frustracao.ipynb) | Prevê o risco de frustração antes que o desempenho colapse. O critério de sucesso não é a acurácia geral, é o recall da classe de risco, porque deixar passar um aluno em risco custa mais do que um alarme falso ocasional. Spark é usado aqui porque o cálculo exige window functions sobre 270 mil interações em ordem cronológica, não por preferência de ferramenta | `PySpark` `XGBoost` `LightGBM` `SHAP` `StratifiedGroupKFold` |

---

## Datasets usados

Todos os datasets desta fase são públicos e autorizados para pesquisa, o que é importante porque o sistema ainda aguarda aprovação regulatória para usar dados de crianças reais.

**CLEAR Corpus** — trechos de texto em inglês com avaliação humana de facilidade de leitura e métrica Flesch-Kincaid. Usado para calibrar a detecção de complexidade textual.

**Bloom's Taxonomy dataset** — exemplos de intenção pedagógica rotulados em inglês. Usado com transferência para português via sistema baseado em regras de verbos, porque um modelo treinado em inglês aplicado diretamente ao português perde precisão nos verbos que definem o nível cognitivo.

**ASSISTments 2009** — log de interações de alunos reais com um sistema tutor americano: acerto, número de tentativas, sequência de habilidades por aluno. Usado nos Núcleos 2 e 3.

**EdNet** — amostra com latência e navegação de alunos em plataforma de ensino coreana. Complementa o ASSISTments com sinal de tempo de resposta.

---

## Relação com a Fase 1

A Fase 1 detecta o estado emocional da criança em tempo real via sensores biométricos. O Motor de Adaptação Curricular usa esse sinal, junto com o grafo de conhecimento e o risco de frustração previsto, para decidir o que adaptar e como. Os dois sistemas se complementam: um sem o outro resolve só parte do problema.

A integração está planejada para depois que a Fase 1 receber aprovação regulatória para operar com crianças reais.

---

## Status

Este repositório está em desenvolvimento ativo. Os três núcleos de análise estão implementados e documentados. A próxima etapa é o módulo de adaptação em si, que usa as saídas dos três núcleos para reescrever automaticamente o texto da atividade preservando o conteúdo pedagógico.

---

**Maria Clara Ribeiro Di Bragança** — SENAI FATESG, Goiânia, GO

> Fase 1 do projeto em [cognikids](https://github.com/mariaclbraganca/cognikids).
