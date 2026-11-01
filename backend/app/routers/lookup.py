import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from ..models import DETAIL_FIELDS, DetailField, FoundDetails, LookupResult
from ..ratelimit import RateLimiter
from ..services import bgg, catalog, llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/lookup", tags=["lookup"])
limiter = RateLimiter(limit=40, window_seconds=300)

BGG_FAILED = "BoardGameGeek did not answer, so its details are missing."


@router.get("", dependencies=[Depends(limiter)])
async def lookup(
    q: str = Query(min_length=1, max_length=120),
    expansion_for: str | None = Query(default=None, max_length=200),
) -> LookupResult:
    """Find candidate games by name: the local catalog, then BGG's search, then an LLM
    web search. Catalog matches get their details from BGG.

    `expansion_for` names the base game when looking for one of its expansions.
    """
    query = q.strip()
    base = (expansion_for or "").strip() or None
    warnings: list[str] = []

    if catalog.is_available():
        candidates = await asyncio.to_thread(
            catalog.search, query, expansions_first=base is not None
        )
        if candidates:
            if bgg.is_configured():
                try:
                    candidates = await bgg.enrich(candidates)
                except Exception:
                    logger.exception("BGG details failed for %r", query)
                    warnings.append(BGG_FAILED)
            return LookupResult(candidates=candidates, warnings=warnings)
    else:
        warnings.append("The game catalog file (boardgames_ranks.csv) is missing.")

    if bgg.is_configured():
        try:
            candidates = await bgg.search(query, expansions_first=base is not None)
            if candidates:
                return LookupResult(candidates=candidates, warnings=warnings)
        except Exception:
            logger.exception("BGG search failed for %r", query)

    if llm.is_configured():
        try:
            candidates, searched = await llm.lookup_candidates(query, base)
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
    expansion_for: str | None = Query(default=None, max_length=200),
    want: list[DetailField] = Query(default=list(DETAIL_FIELDS)),
) -> FoundDetails:
    """A game's `want`ed details: cover, players and play time. BGG answers first, and
    the LLM is asked only for what BGG did not have.

    For an expansion of `expansion_for`, the LLM gives players and time with it added.
    """
    found = FoundDetails()
    if bgg_id and bgg.is_configured():
        try:
            thing = await bgg.thing(bgg_id)
        except Exception:
            logger.exception("BGG details failed for id %s", bgg_id)
            thing = None
        if thing:
            found = FoundDetails(**{field: getattr(thing, field) for field in want})

    missing = [field for field in want if getattr(found, field) is None]
    if not missing:
        return found
    if not llm.is_configured():
        if missing != want:
            return found
        raise HTTPException(503, llm.not_configured_message())
    try:
        base = (expansion_for or "").strip() or None
        from_ai = await llm.fetch_details(name.strip(), year, bgg_id, base, wanted=missing)
    except Exception as exc:
        logger.exception("LLM details lookup failed for %r", name)
        message = llm.error_message(exc, "Could not look this game up.")
        if missing != want:
            return found  # BGG's part is still worth having
        raise HTTPException(502, message) from exc
    filled = {field: getattr(from_ai, field) for field in missing}
    return found.model_copy(
        update={**filled, "searched": from_ai.searched, "used_ai": True}
    )
