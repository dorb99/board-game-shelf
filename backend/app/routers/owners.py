from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlmodel import Session, select

from ..db import get_session
from ..models import Owner, OwnerCreate

router = APIRouter(prefix="/api/owners", tags=["owners"])


def find_owner_by_name(session: Session, name: str) -> Owner | None:
    statement = select(Owner).where(func.lower(Owner.name) == name.strip().lower())
    return session.exec(statement).first()


@router.get("")
def list_owners(session: Session = Depends(get_session)) -> list[Owner]:
    return list(session.exec(select(Owner).order_by(func.lower(Owner.name))))


@router.post("", status_code=201)
def create_owner(data: OwnerCreate, session: Session = Depends(get_session)) -> Owner:
    name = data.name.strip()
    if not name:
        raise HTTPException(422, "Owner name cannot be blank.")
    if find_owner_by_name(session, name):
        raise HTTPException(409, "That owner already exists.")
    owner = Owner(name=name)
    session.add(owner)
    session.commit()
    session.refresh(owner)
    return owner
