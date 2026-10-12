from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Game, GameCreate, GameRead, GameUpdate, Owner
from ..services import images
from .owners import find_owner_by_name

router = APIRouter(prefix="/api/games", tags=["games"])

DETAIL_FIELDS = ("min_players", "max_players", "playing_time")


def resolve_owner(session: Session, owner_id: int | None, owner_name: str | None) -> Owner:
    """Find the owner by id or name; a new name gives an unsaved Owner."""
    if owner_id is not None:
        owner = session.get(Owner, owner_id)
        if owner is None:
            raise HTTPException(404, "Owner not found.")
        return owner
    name = (owner_name or "").strip()
    if not name:
        raise HTTPException(422, "Choose an owner or enter a new owner name.")
    return find_owner_by_name(session, name) or Owner(name=name)


def assert_not_owned(session: Session, owner: Owner, name: str, ignore_id: int | None = None):
    if owner.id is None:
        return
    statement = select(Game).where(
        Game.owner_id == owner.id, func.lower(Game.name) == name.lower()
    )
    existing = session.exec(statement).first()
    if existing and existing.id != ignore_id:
        raise HTTPException(409, f"{owner.name} already has {existing.name}.")


def get_game_or_404(session: Session, game_id: int) -> Game:
    game = session.get(Game, game_id)
    if game is None:
        raise HTTPException(404, "Game not found.")
    return game


@router.get("")
def list_games(
    owner_id: int | None = None, session: Session = Depends(get_session)
) -> list[GameRead]:
    statement = select(Game).order_by(func.lower(Game.name))
    if owner_id is not None:
        statement = statement.where(Game.owner_id == owner_id)
    return [GameRead.from_game(game) for game in session.exec(statement)]


@router.post("", status_code=201)
async def create_game(data: GameCreate, session: Session = Depends(get_session)) -> GameRead:
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "Game name cannot be blank.")
    owner = resolve_owner(session, data.owner_id, data.owner_name)
    assert_not_owned(session, owner, name)

    fields = data.model_dump(exclude={"name", "owner_id", "owner_name", "image_url"})

    image_path = None
    if data.image_url:
        try:
            image_path = await images.save_cover(data.image_url)
        except images.ImageError as exc:
            raise HTTPException(422, str(exc)) from exc

    session.add(owner)
    session.flush()
    game = Game(name=name, owner_id=owner.id, image_path=image_path, **fields)
    session.add(game)
    session.commit()
    session.refresh(game)
    return GameRead.from_game(game)


@router.patch("/{game_id}")
def update_game(
    game_id: int, data: GameUpdate, session: Session = Depends(get_session)
) -> GameRead:
    game = get_game_or_404(session, game_id)
    changes = data.model_dump(exclude_unset=True)

    if changes.get("owner_id") is not None or changes.get("owner_name"):
        owner = resolve_owner(session, data.owner_id, data.owner_name)
        assert_not_owned(session, owner, game.name, ignore_id=game.id)
        session.add(owner)
        session.flush()
        game.owner_id = owner.id

    for key in (*DETAIL_FIELDS, "spine_position"):
        if key in changes:
            setattr(game, key, changes[key])
    if changes.get("spine_label") is not None:
        game.spine_label = changes["spine_label"]
    if game.min_players and game.max_players and game.min_players > game.max_players:
        raise HTTPException(422, "Minimum players cannot exceed maximum players.")

    session.add(game)
    session.commit()
    session.refresh(game)
    return GameRead.from_game(game)


@router.delete("/{game_id}", status_code=204)
def delete_game(game_id: int, session: Session = Depends(get_session)) -> None:
    game = get_game_or_404(session, game_id)
    image_path = game.image_path
    session.delete(game)
    session.commit()
    images.delete_cover(image_path)
