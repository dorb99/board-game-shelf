from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


class Owner(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)


class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    owner_id: int = Field(foreign_key="owner.id", index=True)
    bgg_id: int | None = None
    year: int | None = None
    min_players: int | None = None
    max_players: int | None = None
    playing_time: int | None = None  # minutes
    description: str | None = None
    image_path: str | None = None  # file name inside the covers directory
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


Players = PydanticField(default=None, ge=1, le=999)
Minutes = PydanticField(default=None, ge=1, le=100_000)
OwnerName = PydanticField(min_length=1, max_length=60)


class OwnerCreate(BaseModel):
    name: str = OwnerName


class GameRead(BaseModel):
    id: int
    name: str
    owner_id: int
    bgg_id: int | None
    year: int | None
    min_players: int | None
    max_players: int | None
    playing_time: int | None
    description: str | None
    image_url: str | None

    @classmethod
    def from_game(cls, game: Game) -> "GameRead":
        return cls(
            **game.model_dump(exclude={"image_path", "created_at"}),
            image_url=f"/media/covers/{game.image_path}" if game.image_path else None,
        )


class GameCreate(BaseModel):
    name: str = PydanticField(min_length=1, max_length=200)
    owner_id: int | None = None
    owner_name: str | None = PydanticField(default=None, min_length=1, max_length=60)
    bgg_id: int | None = None
    year: int | None = None
    min_players: int | None = Players
    max_players: int | None = Players
    playing_time: int | None = Minutes
    description: str | None = PydanticField(default=None, max_length=5000)
    image_url: str | None = PydanticField(default=None, max_length=2000)


class GameUpdate(BaseModel):
    owner_id: int | None = None
    owner_name: str | None = PydanticField(default=None, min_length=1, max_length=60)
    min_players: int | None = Players
    max_players: int | None = Players
    playing_time: int | None = Minutes


class Candidate(BaseModel):
    source: Literal["catalog", "gemini"]
    bgg_id: int | None = None
    name: str
    year: int | None = None
    is_expansion: bool = False
    min_players: int | None = None
    max_players: int | None = None
    playing_time: int | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    image_url: str | None = None


class FoundDetails(BaseModel):
    """What Gemini found online for one game; unknown values are null."""

    min_players: int | None = None
    max_players: int | None = None
    playing_time: int | None = None
    description: str | None = None
    image_url: str | None = None


class LookupResult(BaseModel):
    candidates: list[Candidate]
    warnings: list[str] = []


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    text: str = PydanticField(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = PydanticField(min_length=1, max_length=40)
