from contextlib import asynccontextmanager

from pathlib import PurePath

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from sqlmodel import Session

from .config import settings
from .db import create_tables, get_session
from .models import Cover
from .routers import chat, games, lookup, owners
from .services.images import MEDIA_TYPES


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title="Board Games Library", lifespan=lifespan)
app.include_router(owners.router)
app.include_router(games.router)
app.include_router(lookup.router)
app.include_router(chat.router)


@app.get("/media/covers/{name}", include_in_schema=False)
def cover(name: str, session: Session = Depends(get_session)) -> Response:
    found = session.get(Cover, name)
    if found is None:
        raise HTTPException(404)
    return Response(
        found.data,
        media_type=MEDIA_TYPES.get(PurePath(name).suffix),
        # A cover never changes: a new image gets a new name.
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


# In production the built React app is served from the same process.
if settings.frontend_dist.is_dir():
    dist = settings.frontend_dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "media/")):
            raise HTTPException(404)
        file = (dist / path).resolve()
        if file.is_file() and file.is_relative_to(dist):
            return FileResponse(file)
        return FileResponse(dist / "index.html")
