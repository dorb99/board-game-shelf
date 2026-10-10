import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..db import get_session
from ..models import ChatRequest, Game
from ..ratelimit import RateLimiter
from ..services import gemini
from .games import get_game_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/games", tags=["chat"])
limiter = RateLimiter(limit=30, window_seconds=300)


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream(game: Game, request: ChatRequest) -> AsyncIterator[str]:
    try:
        async for event in gemini.stream_rules_answer(game, request.messages):
            yield _event(event)
    except Exception:
        logger.exception("Rules chat failed for game %s", game.id)
        yield _event({"type": "error", "message": "The rules assistant hit an error."})
    yield _event({"type": "done"})


@router.post("/{game_id}/chat", dependencies=[Depends(limiter)])
async def chat(
    game_id: int, request: ChatRequest, session: Session = Depends(get_session)
) -> StreamingResponse:
    """Answer a rules question as a server-sent event stream."""
    game = get_game_or_404(session, game_id)
    if request.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be from the user.")
    if not gemini.is_configured():
        raise HTTPException(503, "Gemini API key is not configured on the server.")
    return StreamingResponse(
        _stream(game, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
