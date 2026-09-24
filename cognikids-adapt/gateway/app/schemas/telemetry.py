from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal["step_completed", "audio_played", "abandoned", "hint_requested"]


class TelemetryEvent(BaseModel):
    """Evento de interação do aluno com uma atividade adaptada.

    Fonte de dado fino que alimenta as arestas do Grafo de Conhecimento
    (ver `workers/knowledge_graph.py`). `concept` e `correct` só fazem
    sentido em `event_type="step_completed"` sobre um passo avaliável — o
    app do aluno decide se o passo tem certo/errado e a qual conceito
    cognitivo ele se refere; nem todo passo tem essa informação (ex: um
    passo puramente de leitura não tem resposta certa/errada), por isso os
    dois campos são opcionais em vez de obrigatórios.
    """

    event_id: str
    student_id: str
    activity_id: str
    session_id: str
    event_type: EventType
    step_number: int | None = None
    concept: str | None = None
    correct: bool | None = None
    duration_ms: int
    timestamp: datetime
    metadata: dict[str, Any] = {}


class TelemetryEventAccepted(BaseModel):
    event_id: str
    ingested: bool
