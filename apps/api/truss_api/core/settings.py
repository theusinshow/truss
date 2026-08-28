from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[4]


def _read_root_env() -> dict[str, str]:
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


class Settings(BaseSettings):
    app_name: str = "Truss Agent"
    environment: str = "local"
    data_dir: Path = REPO_ROOT / "data"
    ai_provider: Literal["auto", "local", "openai"] = "local"
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("TRUSS_OPENAI_API_KEY", "OPENAI_API_KEY"),
    )
    openai_org_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRUSS_OPENAI_ORG_ID", "OPENAI_ORG_ID", "OPENAI_ORGANIZATION"),
    )
    openai_project_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TRUSS_OPENAI_PROJECT_ID", "OPENAI_PROJECT_ID", "OPENAI_PROJECT"),
    )
    openai_model: str = "gpt-5.6-sol"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    openai_max_output_tokens: int = 900

    model_config = SettingsConfigDict(
        env_prefix="TRUSS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
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

    @property
    def geometry_dir(self) -> Path:
        return self.data_dir / "geometry"

    def model_post_init(self, __context: object) -> None:
        root_env = _read_root_env()
        truss_openai_api_key = os.getenv("TRUSS_OPENAI_API_KEY") or root_env.get("TRUSS_OPENAI_API_KEY")
        truss_openai_org_id = os.getenv("TRUSS_OPENAI_ORG_ID") or root_env.get("TRUSS_OPENAI_ORG_ID")
        truss_openai_project_id = os.getenv("TRUSS_OPENAI_PROJECT_ID") or root_env.get("TRUSS_OPENAI_PROJECT_ID")
        current_openai_api_key = self.openai_api_key.get_secret_value() if self.openai_api_key else None
        generic_openai_keys = {
            value
            for value in (os.getenv("OPENAI_API_KEY"), root_env.get("OPENAI_API_KEY"))
            if value
        }
        explicit_openai_api_key = "openai_api_key" in self.__pydantic_fields_set__

        if truss_openai_api_key and (
            current_openai_api_key in generic_openai_keys
            or (not explicit_openai_api_key and current_openai_api_key is None)
        ):
            self.openai_api_key = SecretStr(truss_openai_api_key)

        if truss_openai_org_id:
            self.openai_org_id = truss_openai_org_id

        if truss_openai_project_id:
            self.openai_project_id = truss_openai_project_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
