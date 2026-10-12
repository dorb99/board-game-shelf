import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import FoundDetails, LookupResult
from ..ratelimit import RateLimiter
from ..services import catalog, llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lookup", tags=["lookup"])
limiter = RateLimiter(limit=40, window_seconds=300)


@router.get("", dependencies=[Depends(limiter)])
async def lookup(q: str = Query(min_length=1, max_length=120)) -> LookupResult:
    """Find candidate games by name: the local catalog first, an LLM web search otherwise."""
    query = q.strip()
    warnings: list[str] = []

    if catalog.is_available():
        candidates = await asyncio.to_thread(catalog.search, query)
        if candidates:
            return LookupResult(candidates=candidates)
    else:
        warnings.append("The game catalog file (boardgames_ranks.csv) is missing.")

    if llm.is_configured():
        try:
            candidates, searched = await llm.lookup_candidates(query)
            if not searched:
                warnings.append(llm.not_searched_message())
            return LookupResult(candidates=candidates, warnings=warnings)
        except Exception as exc:
            logger.exception("LLM lookup failed for %r", query)
            warnings.append(llm.error_message(exc, "The web search failed."))
    else:
        warnings.append(llm.not_configured_message())

    return LookupResult(candidates=[], warnings=warnings)


@router.get("/details", dependencies=[Depends(limiter)])
async def details(
    name: str = Query(min_length=1, max_length=200),
    year: int | None = None,
    bgg_id: int | None = None,
) -> FoundDetails:
    """Ask the LLM for a game's cover, players and play time."""
    if not llm.is_configured():
        raise HTTPException(503, llm.not_configured_message())
    try:
        return await llm.fetch_details(name.strip(), year, bgg_id)
    except Exception as exc:
        logger.exception("LLM details lookup failed for %r", name)
        message = llm.error_message(exc, "Could not look this game up.")
        raise HTTPException(502, message) from exc
