"""Game lookups and the rules assistant, on whichever LLM provider LLM_PROVIDER selects."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Protocol

from ..config import settings
from ..models import Candidate, ChatMessage, FoundDetails, Game
from . import images

logger = logging.getLogger(__name__)

LOOKUP_PROMPT = """Search the web for the board game "{query}".
Return up to 4 published board games that best match that name (different games or
major editions, not expansions unless the name asks for one).
Answer with ONLY a JSON array, no prose, where each element is:
{{"name": str, "year": int|null, "min_players": int|null, "max_players": int|null,
"playing_time": int|null (minutes),
"image_urls": [str] (up to 3 direct links to box cover image files, jpg/png/webp)}}"""

DETAILS_PROMPT = """Search the web for the board game "{name}"{year}{bgg}.
Answer with ONLY a JSON object, no prose:
{{"min_players": int|null, "max_players": int|null, "playing_time": int|null,
"image_urls": [str] (up to 4 direct links to box cover image files, jpg/png/webp)}}
playing_time is the typical play time in minutes. Use null when you cannot find a value."""

RULES_SYSTEM = """You are the rules assistant for the board game "{name}"{year}{bgg}.
Search the web for the official rulebook, publisher FAQs and errata, and well
regarded rules references before answering. Answer only questions about this game:
its rules, setup, scoring, edge cases, variants and strategy basics.
Be concise and practical, as if helping people at the table mid-game. Use short
markdown lists for multi-step procedures. If the rules differ between editions, or you
could not confirm something, say so plainly instead of guessing."""

UNSEARCHED_RULES_NOTE = """
Web search is unavailable right now, so ignore the instruction to search and answer
from what you know. Be explicit about anything you are not sure of."""


class Provider(Protocol):
    """One LLM service. `search` asks it to ground the answer in a live web search."""

    label: str

    def is_configured(self) -> bool: ...

    async def generate_json(self, prompt: str, *, search: bool) -> str:
        """Answer a prompt that asks for JSON; the reply may still wrap it in prose."""
        ...

    def stream(
        self, system: str, messages: list[ChatMessage], *, search: bool
    ) -> AsyncIterator[dict]:
        """Yield {"type": "text"} events, then at most one {"type": "sources"} event."""
        ...

    def quota_exceeded(self, exc: Exception) -> bool: ...

    def out_of_credit(self, exc: Exception) -> bool:
        """The account has no API credit at all, so retrying or skipping search won't help."""
        ...

    def overloaded(self, exc: Exception) -> bool: ...


@lru_cache(maxsize=1)
def get_provider() -> Provider:
    """The provider chosen by LLM_PROVIDER; one shared instance keeps its client alive."""
    if settings.llm_provider == "openai":
        from .llm_openai import OpenAIProvider

        return OpenAIProvider()
    from .llm_gemini import GeminiProvider

    return GeminiProvider()


def is_configured() -> bool:
    return get_provider().is_configured()


def not_configured_message() -> str:
    return f"{get_provider().label} API key is not configured on the server."


def not_searched_message() -> str:
    label = get_provider().label
    return (
        f"{label} web search is not available on this API key (quota exceeded; it may "
        f"need billing enabled), so this comes from {label}'s own knowledge and was not "
        "checked online."
    )


def error_message(exc: Exception, fallback: str) -> str:
    """A message worth showing the user for a failed LLM call."""
    provider = get_provider()
    if provider.out_of_credit(exc):
        return (
            f"The {provider.label} API account has no credit. Add API credits in its "
            "billing settings (a chat subscription does not include API usage)."
        )
    if provider.quota_exceeded(exc):
        return f"{provider.label} quota exceeded. Check the API key's plan, or try again in a minute."
    if provider.overloaded(exc):
        return f"{provider.label} is slow or overloaded right now. Try again in a moment."
    if isinstance(exc, NoAnswer):
        return f"{provider.label} gave an unusable answer. Try again."
    return fallback


class NoAnswer(ValueError):
    """The model replied, but not with the JSON it was asked for."""


def extract_json(text: str):
    """Pull the first JSON array or object out of a model reply."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        logger.warning("Model reply had no JSON: %r", text[:500])
        raise NoAnswer("No JSON in model reply")
    start = min(starts)
    end = max(text.rfind("]"), text.rfind("}"))
    return json.loads(text[start : end + 1])


def _positive_int(value) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


async def _searched_json(prompt: str) -> tuple[object, bool]:
    """Ask with web search; if search is refused for quota, ask again without it.

    Returns the parsed JSON and whether the web was actually searched.
    """
    provider = get_provider()
    try:
        return extract_json(await provider.generate_json(prompt, search=True)), True
    except Exception as exc:
        if not provider.quota_exceeded(exc):
            raise
    return extract_json(await provider.generate_json(prompt, search=False)), False


async def _first_working_image(urls) -> str | None:
    urls = [u for u in urls if isinstance(u, str)][:4] if isinstance(urls, list) else []
    checks = await asyncio.gather(*(images.is_image_url(u) for u in urls))
    return next((url for url, ok in zip(urls, checks) if ok), None)


async def lookup_candidates(query: str) -> tuple[list[Candidate], bool]:
    """Find games by name; also returns whether the web was actually searched."""
    prompt = LOOKUP_PROMPT.format(query=query.replace('"', "'"))
    data, searched = await _searched_json(prompt)
    if not isinstance(data, list):
        return [], searched
    entries = [e for e in data if isinstance(e, dict) and e.get("name")][:4]
    # Image links recalled from memory are guesses, so only searched ones are used.
    image_urls = await asyncio.gather(
        *(_first_working_image(e.get("image_urls") if searched else None) for e in entries)
    )
    candidates = [
        Candidate(
            source="web",
            name=str(entry["name"])[:200],
            year=_positive_int(entry.get("year")),
            min_players=_positive_int(entry.get("min_players")),
            max_players=_positive_int(entry.get("max_players")),
            playing_time=_positive_int(entry.get("playing_time")),
            thumbnail_url=image_url,
            image_url=image_url,
        )
        for entry, image_url in zip(entries, image_urls)
    ]
    return candidates, searched


async def fetch_details(name: str, year: int | None, bgg_id: int | None) -> FoundDetails:
    """Look up one game's players, play time and a working cover link."""
    prompt = DETAILS_PROMPT.format(
        name=name.replace('"', "'"),
        year=f" ({year})" if year else "",
        bgg=f", BoardGameGeek id {bgg_id}" if bgg_id else "",
    )
    data, searched = await _searched_json(prompt)
    if not isinstance(data, dict):
        return FoundDetails(searched=searched)
    return FoundDetails(
        searched=searched,
        min_players=_positive_int(data.get("min_players")),
        max_players=_positive_int(data.get("max_players")),
        playing_time=_positive_int(data.get("playing_time")),
        # An image link recalled from memory is a guess, so only searched ones are used.
        image_url=await _first_working_image(data.get("image_urls") if searched else None),
    )


async def stream_rules_answer(
    game: Game, messages: list[ChatMessage]
) -> AsyncIterator[dict]:
    """Yield {"type": "text"} events as the answer streams, then one "sources" event.

    If web search is refused for quota, a "notice" event says so and the answer comes
    from the model's own knowledge.
    """
    provider = get_provider()
    system = RULES_SYSTEM.format(
        name=game.name,
        year=f" ({game.year})" if game.year else "",
        bgg=f", BoardGameGeek id {game.bgg_id}" if game.bgg_id else "",
    )
    started = False
    try:
        async for event in provider.stream(system, messages, search=True):
            started = True
            yield event
        return
    except Exception as exc:
        if started or not provider.quota_exceeded(exc):
            raise
    yield {"type": "notice", "message": not_searched_message()}
    async for event in provider.stream(system + UNSEARCHED_RULES_NOTE, messages, search=False):
        yield event
