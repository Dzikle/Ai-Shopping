import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    server_port: int
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    postgres_password: str
    opensearch_url: str


def load_settings() -> Settings:
    return Settings(
        server_port=int(os.environ.get("SERVER_PORT", "8080")),
        postgres_host=os.environ.get("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_db=os.environ.get("POSTGRES_DB", "ai_shopping"),
        postgres_user=os.environ.get("POSTGRES_USER", "ai_shopping"),
        postgres_password=os.environ.get("POSTGRES_PASSWORD", "replace_me_locally"),
        opensearch_url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
    )
