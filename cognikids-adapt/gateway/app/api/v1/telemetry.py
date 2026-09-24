from fastapi import APIRouter, Depends, HTTPException

from app.clients.core_client import consentimento_permite_uso_app
from app.core.security import usuario_autenticado
from app.schemas.telemetry import TelemetryEvent, TelemetryEventAccepted
from app.services import telemetry_service

router = APIRouter(prefix="/v1/telemetry", tags=["telemetry"])


@router.post("/events", response_model=TelemetryEventAccepted, status_code=201)
async def registrar_evento(
    evento: TelemetryEvent,
    usuario: dict = Depends(usuario_autenticado),
) -> TelemetryEventAccepted:
    if evento.student_id != usuario.get("user_id"):
        raise HTTPException(status_code=403, detail="student_id não corresponde ao usuário autenticado")

    # Autenticação garante que é o próprio aluno enviando — não garante que
    # o responsável autorizou o uso do app. Sem essa checagem, o satélite
    # aceitava e gravava telemetria de qualquer aluno logado, mesmo com
    # consentimento revogado no core.
    consentimento = await consentimento_permite_uso_app(evento.student_id)
    if consentimento is None:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível confirmar o consentimento junto ao core — tente novamente",
        )
    if not consentimento:
        raise HTTPException(status_code=403, detail="Uso do app não autorizado pelo responsável")

    await telemetry_service.publicar_evento(evento)
    return TelemetryEventAccepted(event_id=evento.event_id, ingested=True)
