import asyncio
import json
import re
from collections.abc import AsyncIterator

from google import genai
from google.genai import types

from ..config import settings
from ..models import Candidate, ChatMessage, FoundDetails, Game
from . import images

SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())

LOOKUP_PROMPT = """Search the web for the board game "{query}".
Return up to 4 published board games that best match that name (different games or
major editions, not expansions unless the name asks for one).
Answer with ONLY a JSON array, no prose, where each element is:
{{"name": str, "year": int|null, "min_players": int|null, "max_players": int|null,
"playing_time": int|null (minutes), "description": str (one or two sentences),
"image_urls": [str] (up to 3 direct links to box cover image files, jpg/png/webp)}}"""

DETAILS_PROMPT = """Search the web for the board game "{name}"{year}{bgg}.
Answer with ONLY a JSON object, no prose:
{{"min_players": int|null, "max_players": int|null, "playing_time": int|null,
"description": str|null (one or two sentences about the game),
"image_urls": [str] (up to 4 direct links to box cover image files, jpg/png/webp)}}
playing_time is the typical play time in minutes. Use null when you cannot find a value."""

RULES_SYSTEM = """You are the rules assistant for the board game "{name}"{year}{bgg}.
Use Google Search to find the official rulebook, publisher FAQs and errata, and well
regarded rules references before answering. Answer only questions about this game:
its rules, setup, scoring, edge cases, variants and strategy basics.
Be concise and practical, as if helping people at the table mid-game. Use short
markdown lists for multi-step procedures. If the rules differ between editions, or you
could not confirm something, say so plainly instead of guessing."""


def is_configured() -> bool:
    return bool(settings.gemini_api_key)


def _client() -> genai.Client:
    return genai.Client(api_key=settings.gemini_api_key)


def extract_json(text: str):
    """Pull the first JSON array or object out of a model reply."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise ValueError("No JSON in model reply")
    start = min(starts)
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start : end + 1])


def _positive_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


async def _grounded_json(prompt: str):
    response = await _client().aio.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[SEARCH_TOOL], temperature=0),
    )
    return extract_json(response.text or "")


async def _first_working_image(urls) -> str | None:
    urls = [u for u in urls if isinstance(u, str)][:4] if isinstance(urls, list) else []
    checks = await asyncio.gather(*(images.is_image_url(u) for u in urls))
    return next((url for url, ok in zip(urls, checks) if ok), None)


async def lookup_candidates(query: str) -> list[Candidate]:
    data = await _grounded_json(LOOKUP_PROMPT.format(query=query.replace('"', "'")))
    if not isinstance(data, list):
        return []
    entries = [e for e in data if isinstance(e, dict) and e.get("name")][:4]
    image_urls = await asyncio.gather(
        *(_first_working_image(e.get("image_urls")) for e in entries)
    )
    return [
        Candidate(
            source="gemini",
            name=str(entry["name"])[:200],
            year=_positive_int(entry.get("year")),
            min_players=_positive_int(entry.get("min_players")),
            max_players=_positive_int(entry.get("max_players")),
            playing_time=_positive_int(entry.get("playing_time")),
            description=str(entry.get("description") or "")[:5000] or None,
            thumbnail_url=image_url,
            image_url=image_url,
        )
        for entry, image_url in zip(entries, image_urls)
    ]


async def fetch_details(name: str, year: int | None, bgg_id: int | None) -> FoundDetails:
    """Look up one game's players, play time, description and a working cover link."""
    prompt = DETAILS_PROMPT.format(
        name=name.replace('"', "'"),
        year=f" ({year})" if year else "",
        bgg=f", BoardGameGeek id {bgg_id}" if bgg_id else "",
    )
    data = await _grounded_json(prompt)
    if not isinstance(data, dict):
        return FoundDetails()
    return FoundDetails(
        min_players=_positive_int(data.get("min_players")),
        max_players=_positive_int(data.get("max_players")),
        playing_time=_positive_int(data.get("playing_time")),
        description=str(data.get("description") or "")[:5000] or None,
        image_url=await _first_working_image(data.get("image_urls")),
    )


async def stream_rules_answer(
    game: Game, messages: list[ChatMessage]
) -> AsyncIterator[dict]:
    """Yield {"type": "text"} events as the answer streams, then one "sources" event."""
    system = RULES_SYSTEM.format(
        name=game.name,
        year=f" ({game.year})" if game.year else "",
        bgg=f", BoardGameGeek id {game.bgg_id}" if game.bgg_id else "",
    )
    contents = [
        types.Content(role=m.role, parts=[types.Part(text=m.text)]) for m in messages
    ]
    stream = await _client().aio.models.generate_content_stream(
        model=settings.gemini_model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system, tools=[SEARCH_TOOL], temperature=0.2
        ),
    )
    sources: dict[str, str] = {}
    async for chunk in stream:
        if chunk.text:
            yield {"type": "text", "text": chunk.text}
        for candidate in chunk.candidates or []:
            metadata = candidate.grounding_metadata
            for grounding in (metadata.grounding_chunks if metadata else None) or []:
                if grounding.web and grounding.web.uri:
                    sources.setdefault(
                        grounding.web.uri, grounding.web.title or grounding.web.uri
                    )
    if sources:
        yield {
            "type": "sources",
            "sources": [{"uri": uri, "title": title} for uri, title in sources.items()],
        }
