from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import create_tables
from .routers import chat, games, lookup, owners


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(title="Board Games Library", lifespan=lifespan)
app.include_router(owners.router)
app.include_router(games.router)
app.include_router(lookup.router)
app.include_router(chat.router)
app.mount("/media/covers", StaticFiles(directory=settings.covers_dir), name="covers")

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
