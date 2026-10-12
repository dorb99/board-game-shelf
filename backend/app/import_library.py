"""Copy a library kept in a data directory (library.db and covers/) into the configured database.

    python -m app.import_library [data directory]

With DATABASE_URL set, owners, games and covers go to that database, which must be empty.
Without it, the cover files are loaded into the SQLite library they belong to.
"""

import sys
from pathlib import Path

from sqlmodel import Session, create_engine, select

from .config import settings, sqlite_url
from .db import create_tables, engine
from .models import Cover, Game, Owner


def import_library(data_dir: Path) -> str:
    create_tables()
    with Session(engine) as target:
        copied = 0
        if sqlite_url(data_dir) != settings.engine_url:
            if target.exec(select(Owner)).first():
                return "The database already has a library; nothing was imported."
            with Session(create_engine(sqlite_url(data_dir))) as source:
                owner_ids = {}
                for old in source.exec(select(Owner)):
                    owner = Owner(name=old.name)
                    target.add(owner)
                    target.flush()
                    owner_ids[old.id] = owner.id
                for old in source.exec(select(Game)):
                    fields = old.model_dump(exclude={"id", "owner_id"})
                    target.add(Game(owner_id=owner_ids[old.owner_id], **fields))
                    copied += 1

        covers = 0
        for file in sorted((data_dir / "covers").glob("*")):
            if file.is_file() and target.get(Cover, file.name) is None:
                target.add(Cover(name=file.name, data=file.read_bytes()))
                covers += 1
        target.commit()
    return f"Imported {copied} games and {covers} covers."


if __name__ == "__main__":
    source_dir = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else settings.data_dir
    if not (source_dir / "library.db").is_file():
        sys.exit(f"No library.db in {source_dir}.")
    print(import_library(source_dir))
