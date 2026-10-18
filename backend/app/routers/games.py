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


def expansions_of(session: Session, game: Game) -> list[Game]:
    statement = select(Game).where(Game.parent_id == game.id).order_by(func.lower(Game.name))
    return list(session.exec(statement)) if game.id is not None else []


def get_base_game(session: Session, parent_id: int, child: Game | None = None) -> Game:
    """The game an expansion is added to; expansions only go one level deep."""
    parent = session.get(Game, parent_id)
    if parent is None:
        raise HTTPException(404, "Base game not found.")
    if parent.parent_id is not None:
        raise HTTPException(422, f"{parent.name} is itself an expansion.")
    if child is not None:
        if parent.id == child.id:
            raise HTTPException(422, "A game cannot be an expansion of itself.")
        if expansions_of(session, child):
            raise HTTPException(422, f"{child.name} has expansions of its own.")
    return parent


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
    if data.parent_id is not None:
        owner = session.get(Owner, get_base_game(session, data.parent_id).owner_id)
    else:
        owner = resolve_owner(session, data.owner_id, data.owner_name)
    assert_not_owned(session, owner, name)

    fields = data.model_dump(exclude={"name", "owner_id", "owner_name", "image_url"})

    image_path = None
    if data.image_url:
        try:
            image_path = await images.save_cover(session, data.image_url)
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

    if "parent_id" in changes:
        if data.parent_id is None:
            game.parent_id = None
        else:
            parent = get_base_game(session, data.parent_id, child=game)
            owner = session.get(Owner, parent.owner_id)
            assert_not_owned(session, owner, game.name, ignore_id=game.id)
            game.parent_id = parent.id
            game.owner_id = parent.owner_id

    if changes.get("owner_id") is not None or changes.get("owner_name"):
        if game.parent_id is not None:
            raise HTTPException(422, "An expansion always belongs to its base game's owner.")
        owner = resolve_owner(session, data.owner_id, data.owner_name)
        # The expansions move with their base game.
        moving = [game, *expansions_of(session, game)]
        for item in moving:
            assert_not_owned(session, owner, item.name, ignore_id=item.id)
        session.add(owner)
        session.flush()
        for item in moving:
            item.owner_id = owner.id
            session.add(item)

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
    # Its expansions go with it, removed first so no row points at a deleted game.
    for expansion in expansions_of(session, game):
        images.delete_cover(session, expansion.image_path)
        session.delete(expansion)
    session.flush()
    images.delete_cover(session, game.image_path)
    session.delete(game)
    session.commit()
