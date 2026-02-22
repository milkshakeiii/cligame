from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./cligame.db"
    tick_interval: float = 1.0

    model_config = {"env_prefix": "CLIGAME_"}


settings = Settings()
