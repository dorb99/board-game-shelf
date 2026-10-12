from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

if settings.engine_url.startswith("sqlite"):
    engine = create_engine(settings.engine_url, connect_args={"check_same_thread": False})
else:
    # Hosted Postgres drops idle connections; check each one before using it.
    engine = create_engine(settings.engine_url, pool_pre_ping=True)


# Columns added after the first release: create_all() never alters an existing table.
ADDED_COLUMNS = {
    "game": {
        "spine_position": "INTEGER",
        "spine_label": "BOOLEAN NOT NULL DEFAULT TRUE",
    },
}


def create_tables() -> None:
    SQLModel.metadata.create_all(engine)
    with engine.begin() as connection:
        for table, columns in ADDED_COLUMNS.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
