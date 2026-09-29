from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HugeCP Threat Intel API"
    database_url: str = "postgresql://hugecp:hugecp@localhost:5433/hugecp"
    cors_origins: list[str] = ["http://localhost:5173"]


settings = Settings()
