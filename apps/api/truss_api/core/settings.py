from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    app_name: str = "Truss Agent"
    environment: str = "local"
    data_dir: Path = REPO_ROOT / "data"

    model_config = SettingsConfigDict(
        env_prefix="TRUSS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def db_dir(self) -> Path:
        return self.data_dir / "db"

    @property
    def database_path(self) -> Path:
        return self.db_dir / "truss.sqlite"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals"

    @property
    def renders_dir(self) -> Path:
        return self.data_dir / "renders"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
