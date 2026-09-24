from app.clients import rabbitmq
from app.schemas.telemetry import TelemetryEvent


async def publicar_evento(evento: TelemetryEvent) -> None:
    payload = evento.model_dump(mode="json")
    await rabbitmq.publish("telemetry", payload)
