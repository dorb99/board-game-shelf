"""BoardGameGeek's XML API2: game details by id, and name search for games the catalog lacks.

Needs an approved application token (boardgamegeek.com/applications) in BGG_API_TOKEN.
"""

import asyncio
import logging
import time
import xml.etree.ElementTree as ET
from typing import NamedTuple

import httpx

from ..config import settings
from ..models import Candidate
from . import catalog

logger = logging.getLogger(__name__)

API_URL = "https://boardgamegeek.com/xmlapi2"  # BGG rejects tokens sent to www.
MAX_IDS = 20  # most ids one /thing request takes
MAX_CANDIDATES = 8
# BGG answers 202 while it prepares a reply, and 429/500/503 when asked too often.
RETRY_STATUSES = {202, 429, 500, 503}
RETRY_DELAYS = (1, 2, 4)
MIN_SPACING = 1.0  # seconds between requests, to stay well under BGG's throttling
CACHE_SECONDS = 24 * 60 * 60
CACHE_SIZE = 2000


class Thing(NamedTuple):
    bgg_id: int
    name: str
    year: int | None
    is_expansion: bool
    min_players: int | None
    max_players: int | None
    playing_time: int | None  # minutes
    image_url: str | None
    thumbnail_url: str | None

    def candidate(self) -> Candidate:
        return Candidate(source="bgg", **self._asdict())


class BggError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.bgg_api_token)


_cache: dict[int, tuple[float, Thing]] = {}
_lock = asyncio.Lock()
_last_request = 0.0


def _positive_int(value: str | None) -> int | None:
    try:
        number = int(value or 0)
    except ValueError:
        return None
    return number if number > 0 else None  # BGG uses 0 for unknown


def _value(item: ET.Element, tag: str) -> str | None:
    element = item.find(tag)
    return element.get("value") if element is not None else None


def _text(item: ET.Element, tag: str) -> str | None:
    text = (item.findtext(tag) or "").strip()
    return text or None


def _primary_name(item: ET.Element) -> str | None:
    names = item.findall("name")
    primary = next((n for n in names if n.get("type") == "primary"), names[0] if names else None)
    return primary.get("value") if primary is not None else None


def parse_things(xml: str) -> list[Thing]:
    things = []
    for item in ET.fromstring(xml).iter("item"):
        name = _primary_name(item)
        if not name or not (item.get("id") or "").isdigit():
            continue
        things.append(
            Thing(
                bgg_id=int(item.get("id")),
                name=name,
                year=_positive_int(_value(item, "yearpublished")),
                is_expansion=item.get("type") == "boardgameexpansion",
                min_players=_positive_int(_value(item, "minplayers")),
                max_players=_positive_int(_value(item, "maxplayers")),
                playing_time=_positive_int(_value(item, "playingtime"))
                or _positive_int(_value(item, "maxplaytime")),
                image_url=_text(item, "image"),
                thumbnail_url=_text(item, "thumbnail"),
            )
        )
    return things


def parse_search(xml: str) -> list[tuple[int, str]]:
    """(id, name) of each search hit, in BGG's order."""
    hits = []
    for item in ET.fromstring(xml).iter("item"):
        name = _primary_name(item)
        if name and (item.get("id") or "").isdigit():
            hits.append((int(item.get("id")), name))
    return hits


async def _get(path: str, params: dict) -> str:
    """One API call, spaced from the last and retried while BGG is busy."""
    global _last_request
    headers = {
        "Authorization": f"Bearer {settings.bgg_api_token}",
        "User-Agent": "BoardGamesLibrary/1.0",
    }
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for delay in (*RETRY_DELAYS, None):
            async with _lock:
                wait = _last_request + MIN_SPACING - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                try:
                    response = await client.get(f"{API_URL}/{path}", params=params)
                except httpx.HTTPError as exc:
                    raise BggError(f"Could not reach BoardGameGeek: {exc}") from exc
                finally:
                    _last_request = time.monotonic()
            if response.status_code == 200:
                return response.text
            if response.status_code not in RETRY_STATUSES or delay is None:
                raise BggError(f"BoardGameGeek answered {response.status_code}.")
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")


def _cached(bgg_id: int) -> Thing | None:
    hit = _cache.get(bgg_id)
    return hit[1] if hit and time.monotonic() - hit[0] < CACHE_SECONDS else None


async def things(ids: list[int]) -> dict[int, Thing]:
    """Details for these game ids; ids BGG does not know are left out."""
    found = {i: thing for i in ids if (thing := _cached(i))}
    missing = list(dict.fromkeys(i for i in ids if i not in found))
    for start in range(0, len(missing), MAX_IDS):
        batch = missing[start : start + MAX_IDS]
        xml = await _get("thing", {"id": ",".join(map(str, batch))})
        if len(_cache) > CACHE_SIZE:
            _cache.clear()
        for thing in parse_things(xml):
            _cache[thing.bgg_id] = (time.monotonic(), thing)
            found[thing.bgg_id] = thing
    return found


async def thing(bgg_id: int) -> Thing | None:
    return (await things([bgg_id])).get(bgg_id)


async def enrich(candidates: list[Candidate]) -> list[Candidate]:
    """Fill catalog matches in with BGG's players, play time and cover."""
    found = await things([c.bgg_id for c in candidates if c.bgg_id])
    return [
        found[c.bgg_id].candidate() if c.bgg_id in found else c for c in candidates
    ]


async def search(query: str, expansions_first: bool = False) -> list[Candidate]:
    """Games and expansions BGG finds by name, closest match first, with their details."""
    xml = await _get("search", {"query": query, "type": "boardgame,boardgameexpansion"})
    wanted = catalog.normalize(query)
    rank = {}  # id -> (match quality, BGG's order); a hit matched by another name ranks last
    for order, (bgg_id, name) in enumerate(dict(parse_search(xml)).items()):
        quality = catalog.match_quality(catalog.normalize(name), wanted)
        rank[bgg_id] = (99 if quality is None else quality, order)
    # Search hits do not reliably say which are expansions, so the details decide that.
    ids = sorted(rank, key=rank.get)[:MAX_IDS]
    found = list((await things(ids)).values())
    if expansions_first:
        found.sort(key=lambda t: (not t.is_expansion, rank[t.bgg_id]))
    else:
        found.sort(key=lambda t: (rank[t.bgg_id][0], t.is_expansion, rank[t.bgg_id][1]))
    return [t.candidate() for t in found[:MAX_CANDIDATES]]
