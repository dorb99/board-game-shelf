from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-flash-latest"
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

    @property
    def covers_dir(self) -> Path:
        return self.data_dir / "covers"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{(self.data_dir / 'library.db').as_posix()}"


settings = Settings()
settings.covers_dir.mkdir(parents=True, exist_ok=True)
