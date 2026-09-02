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
    backup_dir: Path = REPO_ROOT / "backups"
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
    vision_enabled: bool = False
    vision_budget_usd_per_revision: float = Field(default=0.25, ge=0.0)
    vision_max_calls_per_revision: int = Field(default=30, ge=1)
    vision_max_candidates_per_sheet: int = Field(default=8, ge=1, le=50)
    vision_cost_reserve_usd_per_call: float = Field(default=0.05, gt=0.0)
    vision_small_text_threshold_pt: float = Field(default=5.5, gt=0.0)
    vision_min_confidence: float = Field(default=0.65, ge=0.0, le=1.0)
    vision_crop_padding_pt: float = Field(default=18.0, ge=0.0)
    vision_render_scale: float = Field(default=3.0, gt=0.0)
    vision_max_crop_pixels: int = Field(default=1600, ge=256, le=4096)
    vision_image_detail: Literal["low", "high", "original"] = "high"
    vision_max_output_tokens: int = Field(default=600, ge=100, le=4000)
    batch_poll_interval_seconds: float = Field(default=0.5, ge=0.1, le=10.0)

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
    def database_recovery_dir(self) -> Path:
        return self.db_dir / "recovery"

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

    @property
    def calibration_dir(self) -> Path:
        return self.data_dir / "calibration"

    @property
    def calibration_analyses_dir(self) -> Path:
        return self.calibration_dir / "analyses"

    @property
    def calibration_runs_dir(self) -> Path:
        return self.calibration_dir / "runs"

    @property
    def calibration_exports_dir(self) -> Path:
        return self.calibration_dir / "exports"

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
