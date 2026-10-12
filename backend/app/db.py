import ssl
from collections.abc import Iterator

from sqlalchemy import inspect, make_url, text
from sqlmodel import Session, SQLModel, create_engine

from .config import settings


def _create_engine(database_url: str):
    url = make_url(database_url)
    connect_args = {}
    if url.drivername.startswith("postgres"):
        # pg8000 is pure Python, so it runs where compiled drivers are blocked. It takes
        # TLS as a context instead of the sslmode option that hosts put in the URL.
        if url.query.get("sslmode", "disable") != "disable":
            connect_args["ssl_context"] = ssl.create_default_context()
        url = url.set(drivername="postgresql+pg8000", query={})
    # Hosted Postgres drops idle connections; check each one before using it.
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = _create_engine(settings.database_url)


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
