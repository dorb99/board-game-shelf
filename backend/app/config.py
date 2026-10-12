from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    # Which service answers lookups and rules questions.
    llm_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    # Reasoning models only; leave blank for a model that does not take this setting.
    openai_reasoning_effort: str = "low"
    # Postgres connection string for the library: owners, games and cover images.
    database_url: str
    # Where the game catalog file lives.
    data_dir: Path = BACKEND_DIR / "data"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    @field_validator("data_dir", "frontend_dist")
    @classmethod
    def _relative_to_project(cls, path: Path) -> Path:
        """Relative paths mean the same place whatever directory the server starts in."""
        return path if path.is_absolute() else BACKEND_DIR.parent / path

    @property
    def catalog_csv(self) -> Path:
        """BoardGameGeek ranks export (boardgamegeek.com/data_dumps/bg_ranks)."""
        return self.data_dir / "boardgames_ranks.csv"


settings = Settings()
