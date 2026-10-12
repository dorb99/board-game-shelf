import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from ..db import get_session
from ..models import ChatRequest, Game
from ..ratelimit import RateLimiter
from ..services import llm
from .games import get_game_or_404

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/games", tags=["chat"])
limiter = RateLimiter(limit=30, window_seconds=300)


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _stream(game: Game, request: ChatRequest) -> AsyncIterator[str]:
    try:
        async for event in llm.stream_rules_answer(game, request.messages):
            yield _event(event)
    except Exception as exc:
        logger.exception("Rules chat failed for game %s", game.id)
        message = llm.error_message(exc, "The rules assistant hit an error.")
        yield _event({"type": "error", "message": message})
    yield _event({"type": "done"})


@router.post("/{game_id}/chat", dependencies=[Depends(limiter)])
async def chat(
    game_id: int, request: ChatRequest, session: Session = Depends(get_session)
) -> StreamingResponse:
    """Answer a rules question as a server-sent event stream."""
    game = get_game_or_404(session, game_id)
    if request.messages[-1].role != "user":
        raise HTTPException(422, "The last message must be from the user.")
    if not llm.is_configured():
        raise HTTPException(503, llm.not_configured_message())
    return StreamingResponse(
        _stream(game, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
