from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    database_url: str = "postgresql+psycopg://lab:lab_dev_only@localhost:5432/lab_platform"
    data_root: Path = ROOT / "storage"


@lru_cache
def get_settings() -> Settings:
    return Settings()
