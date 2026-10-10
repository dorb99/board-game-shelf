import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import FoundDetails, LookupResult
from ..ratelimit import RateLimiter
from ..services import catalog, gemini

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lookup", tags=["lookup"])
limiter = RateLimiter(limit=40, window_seconds=300)


@router.get("", dependencies=[Depends(limiter)])
async def lookup(q: str = Query(min_length=1, max_length=120)) -> LookupResult:
    """Find candidate games by name: the local catalog first, Gemini web search otherwise."""
    query = q.strip()
    warnings: list[str] = []

    if catalog.is_available():
        candidates = await asyncio.to_thread(catalog.search, query)
        if candidates:
            return LookupResult(candidates=candidates)
    else:
        warnings.append("The game catalog file (boardgames_ranks.csv) is missing.")

    if gemini.is_configured():
        try:
            return LookupResult(
                candidates=await gemini.lookup_candidates(query), warnings=warnings
            )
        except Exception:
            logger.exception("Gemini lookup failed for %r", query)
            warnings.append("Gemini search failed.")
    else:
        warnings.append("Gemini API key is not configured.")

    return LookupResult(candidates=[], warnings=warnings)


@router.get("/details", dependencies=[Depends(limiter)])
async def details(
    name: str = Query(min_length=1, max_length=200),
    year: int | None = None,
    bgg_id: int | None = None,
) -> FoundDetails:
    """Ask Gemini for a game's cover, players, play time and description."""
    if not gemini.is_configured():
        raise HTTPException(503, "Gemini API key is not configured on the server.")
    try:
        return await gemini.fetch_details(name.strip(), year, bgg_id)
    except Exception:
        logger.exception("Gemini details lookup failed for %r", name)
        raise HTTPException(502, "Gemini could not look this game up.")
