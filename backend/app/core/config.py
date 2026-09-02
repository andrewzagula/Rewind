from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://rewind:rewind@localhost:5432/rewind"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    market_data_provider: str = "stooq"
    market_data_dir: str = "data/market"
    chat_tool_run_timeout_seconds: float = 45.0

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
