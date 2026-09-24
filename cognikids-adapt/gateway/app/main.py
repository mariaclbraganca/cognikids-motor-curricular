from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1 import curriculum, students, telemetry
from app.clients import rabbitmq
from app.db import mongo


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.connect()
    await mongo.ensure_indexes()
    await rabbitmq.connect()
    yield
    await rabbitmq.close()
    mongo.close()


app = FastAPI(title="CogniKids Adapt Gateway", lifespan=lifespan)

app.include_router(curriculum.router)
app.include_router(telemetry.router)
app.include_router(students.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "cognikids-adapt-gateway"}
