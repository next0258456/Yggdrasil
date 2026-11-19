"""Configuration settings for the Y7L Native Track-B sidecar."""

from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables and optional .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    y7l_tools_port: int = 8300
    obsidian_vault_path: str = "./vault"
    data_dir: str = "./data"
    fmcg_sales_parquet_path: str = ""

    jwt_secret: str = "y7l_dev_jwt_secret_change_me_2026"
    jwt_ttl_seconds: int = 36000
    redis_url: str = ""
    superset_url: str = ""

    llm_api_base: str = "http://localhost:4000/v1"
    llm_api_key: str = "sk-yggdrasil-master-admin-2026"
    llm_model: str = "yggdrasil-default-llm"
    embed_model: str = "text-embedding-3-small"
    stt_model: str = "whisper-1"
    tts_voice: str = "vi-VN-HoaiMyNeural"

    dept_monthly_budget_usd: float = 5.0

    @property
    def vault_dir(self) -> Path:
        path = Path(self.obsidian_vault_path)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()

    @property
    def exports_dir(self) -> Path:
        exports = self.data_path / "exports"
        exports.mkdir(parents=True, exist_ok=True)
        return exports

    @property
    def fmcg_sales_file(self) -> Path | None:
        raw = self.fmcg_sales_parquet_path.strip()
        if not raw:
            return None
        path = Path(raw)
        resolved = path if path.is_absolute() else (PROJECT_ROOT / path).resolve()
        return resolved if resolved.is_file() else None


def get_settings() -> Settings:
    """Create a Settings instance from the current environment."""
    return Settings()
