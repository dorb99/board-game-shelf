from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field as PydanticField
from sqlmodel import Field, SQLModel


class Owner(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)


class Cover(SQLModel, table=True):
    """A cover image, kept in the database so it survives on hosts without a disk."""

    name: str = Field(primary_key=True)  # random file name; the extension gives the format
    data: bytes


class Game(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    owner_id: int = Field(foreign_key="owner.id", index=True)
    bgg_id: int | None = None
    year: int | None = None
    min_players: int | None = None
    max_players: int | None = None
    playing_time: int | None = None  # minutes
    image_path: str | None = None  # name of its Cover row
    # Which horizontal strip of the cover shows on the shelf: 0 = top, 100 = bottom.
    spine_position: int | None = None
    spine_label: bool = True  # print the name over the strip
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


Players = PydanticField(default=None, ge=1, le=999)
Minutes = PydanticField(default=None, ge=1, le=100_000)
SpinePosition = PydanticField(default=None, ge=0, le=100)
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
    image_url: str | None
    spine_position: int | None
    spine_label: bool

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
    image_url: str | None = PydanticField(default=None, max_length=2000)
    spine_position: int | None = SpinePosition
    spine_label: bool = True


class GameUpdate(BaseModel):
    owner_id: int | None = None
    owner_name: str | None = PydanticField(default=None, min_length=1, max_length=60)
    min_players: int | None = Players
    max_players: int | None = Players
    playing_time: int | None = Minutes
    spine_position: int | None = SpinePosition
    spine_label: bool | None = None


class Candidate(BaseModel):
    source: Literal["catalog", "web"]
    bgg_id: int | None = None
    name: str
    year: int | None = None
    is_expansion: bool = False
    min_players: int | None = None
    max_players: int | None = None
    playing_time: int | None = None
    thumbnail_url: str | None = None
    image_url: str | None = None


class FoundDetails(BaseModel):
    """What the LLM found online for one game; unknown values are null."""

    min_players: int | None = None
    max_players: int | None = None
    playing_time: int | None = None
    image_url: str | None = None
    searched: bool = True  # False when web search was refused and the LLM answered from memory


class LookupResult(BaseModel):
    candidates: list[Candidate]
    warnings: list[str] = []


class ChatMessage(BaseModel):
    role: Literal["user", "model"]
    text: str = PydanticField(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = PydanticField(min_length=1, max_length=40)
