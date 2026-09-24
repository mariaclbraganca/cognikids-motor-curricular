from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_exchange: str = "cognikids"

    satellite_mongo_uri: str = "mongodb://localhost:27018/cognikids_adapt"

    # Mesmo segredo do Flask core — o gateway valida o JWT que o core emite
    # em vez de ter autenticação própria (ver app/core/security.py)
    core_jwt_secret: str = ""

    # Usados só para consultar consentimento antes de aceitar telemetria
    # (ver app/clients/core_client.py) — mesmo padrão de JWT de serviço já
    # usado pelos workers em cognikids-adapt/workers/core_client.py
    core_base_url: str = "http://localhost:5001"
    core_service_user_id: str = ""

    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8001


settings = Settings()
