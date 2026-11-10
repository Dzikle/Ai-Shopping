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
    assistant_provider: str
    assistant_model: str
    assistant_base_url: str
    assistant_api_key: str
    assistant_max_output_tokens: int
    assistant_timeout_seconds: float
    assistant_rate_limit_requests: int
    assistant_rate_limit_window_seconds: int
    assistant_max_concurrency: int


def load_settings() -> Settings:
    return Settings(
        server_port=int(os.environ.get("SERVER_PORT", "8080")),
        postgres_host=os.environ.get("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        postgres_db=os.environ.get("POSTGRES_DB", "ai_shopping"),
        postgres_user=os.environ.get("POSTGRES_USER", "ai_shopping"),
        postgres_password=os.environ.get("POSTGRES_PASSWORD", "replace_me_locally"),
        opensearch_url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
        assistant_provider=os.environ.get("ASSISTANT_PROVIDER", "").strip().lower(),
        assistant_model=os.environ.get("ASSISTANT_MODEL", "").strip(),
        assistant_base_url=os.environ.get("ASSISTANT_BASE_URL", "").strip().rstrip("/"),
        assistant_api_key=os.environ.get("ASSISTANT_API_KEY", "").strip(),
        assistant_max_output_tokens=int(os.environ.get("ASSISTANT_MAX_OUTPUT_TOKENS", "1024")),
        assistant_timeout_seconds=float(os.environ.get("ASSISTANT_TIMEOUT_SECONDS", "20")),
        assistant_rate_limit_requests=int(os.environ.get("ASSISTANT_RATE_LIMIT_REQUESTS", "30")),
        assistant_rate_limit_window_seconds=int(os.environ.get("ASSISTANT_RATE_LIMIT_WINDOW_SECONDS", "300")),
        assistant_max_concurrency=int(os.environ.get("ASSISTANT_MAX_CONCURRENCY", "4")),
    )
