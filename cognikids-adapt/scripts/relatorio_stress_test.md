# Relatório de Stress Test — Sprint 1

## Metodologia

Emulador de carga (`load_emulator.py`) disparando 100 requisições `POST
/v1/telemetry/events` contra o gateway rodando em Docker Compose (1 réplica,
sem tuning de workers do Uvicorn — configuração padrão), comparando execução
sequencial (uma requisição de cada vez) com execução paralela (100 requisições
concorrentes via `asyncio.gather`).

Ambiente: gateway FastAPI + RabbitMQ + MongoDB TimeSeries, todos em containers
Docker na mesma máquina de desenvolvimento (não é um ambiente de produção
isolado — os números absolutos não são comparáveis a um deploy real, mas a
comparação sequencial vs. paralelo dentro do mesmo ambiente é válida).

## Resultados

| Métrica | Sequencial | Paralelo (100 concorrentes) |
|---|---|---|
| Requisições bem-sucedidas | 100/100 | 100/100 |
| Tempo total | 6,22s | 0,63s |
| Throughput | 16,1 req/s | 159,1 req/s |
| Latência média | 60,2 ms | 490,9 ms |
| Latência p50 | 60,8 ms | 502,3 ms |
| Latência p95 | 69,9 ms | 547,8 ms |
| Latência p99 | 74,4 ms | 553,6 ms |

**Speedup de throughput: 9,9x**

## Interpretação

O throughput agregado aumenta quase 10x com paralelismo — o gateway assíncrono
(FastAPI + `aio-pika`, publicação não bloqueante na fila) processa muito mais
requisições por segundo quando recebidas em paralelo do que uma de cada vez.

A latência **individual**, porém, piora sob carga concorrente (de ~60ms para
~490ms em média). Isso é esperado e não é uma falha do desenho: 100 requisições
simultâneas competem pelo mesmo processo Uvicorn (1 worker, configuração
padrão do Dockerfile atual) e pela mesma conexão RabbitMQ. O sistema não perde
requisições (100/100 bem-sucedidas nos dois cenários), mas cada requisição
individual espera mais para ser atendida quando todas chegam ao mesmo tempo.

## Limitações deste teste

- Não inclui o serviço legado rodando simultaneamente — o critério de aceite
  "100 sessões paralelas sem degradar o legado" (CLAUDE.md seção 14) não foi
  verificado nesta rodada, porque os dois serviços não estavam ativos ao mesmo
  tempo neste ambiente. Esse teste precisa ser refeito com o legado no ar.
- O Uvicorn está rodando com 1 worker (padrão do `Dockerfile` atual, sem
  `--workers N`); aumentar o número de workers é o próximo ajuste óbvio para
  melhorar a latência sob carga, mas não foi testado nesta rodada.
- Testado apenas o endpoint de telemetria; `/v1/curriculum/adapt` não foi
  incluído no teste de carga.

## Próximos passos

- Repetir o teste com o legado ativo, monitorando sua latência simultaneamente.
- Testar com `uvicorn --workers N` para ver o efeito na latência sob carga.
- Incluir `/v1/curriculum/adapt` no emulador de carga.
