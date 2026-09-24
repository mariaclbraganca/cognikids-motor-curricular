"""Emulador de carga (Sprint 1).

Dispara N sessões concorrentes de POST /v1/telemetry/events contra o gateway
e mede a distribuição de latência. Usado para o relatório de stress test
(latência sequencial vs. paralela, ver CLAUDE.md seção 11 — Paralelismo).

Uso:
    python load_emulator.py --sessoes 100 --url http://localhost:8001
"""

import argparse
import asyncio
import statistics
import time
import uuid
from datetime import datetime, timezone

import httpx


def montar_evento(indice: int) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "student_id": f"aluno-carga-{indice}",
        "activity_id": "atividade-carga",
        "session_id": f"sessao-carga-{indice}",
        "event_type": "step_completed",
        "step_number": 1,
        "duration_ms": 1500,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metadata": {"origem": "load_emulator"},
    }


async def disparar_um(cliente: httpx.AsyncClient, url: str, indice: int) -> tuple[float, int]:
    inicio = time.perf_counter()
    resposta = await cliente.post(f"{url}/v1/telemetry/events", json=montar_evento(indice))
    duracao_ms = (time.perf_counter() - inicio) * 1000
    return duracao_ms, resposta.status_code


async def rodar_sequencial(url: str, quantidade: int) -> list[float]:
    latencias = []
    async with httpx.AsyncClient(timeout=30) as cliente:
        for i in range(quantidade):
            duracao_ms, status = await disparar_um(cliente, url, i)
            if status == 201:
                latencias.append(duracao_ms)
    return latencias


async def rodar_paralelo(url: str, quantidade: int) -> list[float]:
    async with httpx.AsyncClient(timeout=30) as cliente:
        resultados = await asyncio.gather(*[disparar_um(cliente, url, i) for i in range(quantidade)])
    return [duracao_ms for duracao_ms, status in resultados if status == 201]


def relatorio(nome: str, latencias: list[float], tempo_total_s: float) -> None:
    if not latencias:
        print(f"{nome}: nenhuma requisição bem-sucedida")
        return
    latencias_ordenadas = sorted(latencias)
    p50 = statistics.median(latencias_ordenadas)
    p95 = latencias_ordenadas[int(len(latencias_ordenadas) * 0.95) - 1]
    p99 = latencias_ordenadas[int(len(latencias_ordenadas) * 0.99) - 1]

    print(f"\n=== {nome} ===")
    print(f"Requisições bem-sucedidas: {len(latencias)}")
    print(f"Tempo total: {tempo_total_s:.2f}s")
    print(f"Throughput: {len(latencias) / tempo_total_s:.1f} req/s")
    print(f"Latência média: {statistics.mean(latencias):.1f} ms")
    print(f"Latência mediana (p50): {p50:.1f} ms")
    print(f"Latência p95: {p95:.1f} ms")
    print(f"Latência p99: {p99:.1f} ms")
    print(f"Latência mínima: {min(latencias):.1f} ms")
    print(f"Latência máxima: {max(latencias):.1f} ms")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessoes", type=int, default=100)
    parser.add_argument("--url", type=str, default="http://localhost:8001")
    args = parser.parse_args()

    print(f"Emulador de carga — {args.sessoes} sessões contra {args.url}")

    inicio_seq = time.perf_counter()
    latencias_seq = await rodar_sequencial(args.url, args.sessoes)
    tempo_seq = time.perf_counter() - inicio_seq
    relatorio(f"Sequencial ({args.sessoes} requisições, uma de cada vez)", latencias_seq, tempo_seq)

    inicio_par = time.perf_counter()
    latencias_par = await rodar_paralelo(args.url, args.sessoes)
    tempo_par = time.perf_counter() - inicio_par
    relatorio(f"Paralelo ({args.sessoes} requisições concorrentes)", latencias_par, tempo_par)

    if latencias_seq and latencias_par:
        print(f"\n=== Comparação ===")
        print(f"Speedup de throughput (paralelo / sequencial): {(tempo_seq / tempo_par):.1f}x")


if __name__ == "__main__":
    asyncio.run(main())
