"""Game lookups and the rules assistant, on whichever LLM provider LLM_PROVIDER selects."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator, Sequence
from functools import lru_cache
from typing import Protocol

from ..config import settings
from ..models import DETAIL_FIELDS, Candidate, ChatMessage, DetailField, FoundDetails, Game
from . import images

logger = logging.getLogger(__name__)

LOOKUP_PROMPT = """Search the web for the board game "{query}".
Return up to 4 published board games that best match that name (different games or
major editions, not expansions unless the name asks for one).
Answer with ONLY a JSON array, no prose, where each element is:
{{"name": str, "year": int|null, "min_players": int|null, "max_players": int|null,
"playing_time": int|null (minutes),
"image_urls": [str] (up to 3 direct links to box cover image files, jpg/png/webp)}}"""

EXPANSION_LOOKUP_PROMPT = """Search the web for expansions of the board game "{base}" that
match the name "{query}".
Return up to 4 published expansions for that game that best match the name.
min_players and max_players are the player counts the game supports once this expansion
is added, and playing_time is the typical play time in minutes with it.
Answer with ONLY a JSON array, no prose, where each element is:
{{"name": str, "year": int|null, "min_players": int|null, "max_players": int|null,
"playing_time": int|null,
"image_urls": [str] (up to 3 direct links to box cover image files, jpg/png/webp)}}"""

DETAILS_PROMPT = """Search the web for the board game "{name}"{year}{bgg}.
Answer with ONLY a JSON object, no prose:
{{{fields}}}
playing_time is the typical play time in minutes. Use null when you cannot find a value."""

EXPANSION_DETAILS_PROMPT = """Search the web for "{name}"{year}{bgg}, an expansion for the
board game "{base}".
Answer with ONLY a JSON object, no prose:
{{{fields}}}
min_players and max_players are the player counts the game supports once this expansion
is added, and playing_time is the typical play time in minutes with it. Use null when you
cannot find a value."""

# How each detail is asked for in the JSON answer.
DETAIL_ANSWERS: dict[DetailField, str] = {
    "min_players": '"min_players": int|null',
    "max_players": '"max_players": int|null',
    "playing_time": '"playing_time": int|null',
    "image_url": '"image_urls": [str] (up to 4 direct links to box cover image files, jpg/png/webp)',
}

RULES_SYSTEM = """You are the rules assistant for the board game "{name}"{year}{bgg}.{context}
Search the web for the official rulebook, publisher FAQs and errata, and well
regarded rules references before answering. Answer only questions about this game
and its expansions: rules, setup, scoring, edge cases, variants and strategy basics.
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


def _quoted(text: str) -> str:
    return text.replace('"', "'")


async def lookup_candidates(
    query: str, expansion_for: str | None = None
) -> tuple[list[Candidate], bool]:
    """Find games by name, or expansions of `expansion_for`; also returns whether the
    web was actually searched."""
    if expansion_for:
        prompt = EXPANSION_LOOKUP_PROMPT.format(query=_quoted(query), base=_quoted(expansion_for))
    else:
        prompt = LOOKUP_PROMPT.format(query=_quoted(query))
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
            is_expansion=bool(expansion_for),
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


async def fetch_details(
    name: str,
    year: int | None,
    bgg_id: int | None,
    expansion_for: str | None = None,
    wanted: Sequence[DetailField] = DETAIL_FIELDS,
) -> FoundDetails:
    """Look up the `wanted` details of one game: players, play time, a working cover link.

    For an expansion of `expansion_for`, the players and time are with it added.
    """
    template = EXPANSION_DETAILS_PROMPT if expansion_for else DETAILS_PROMPT
    prompt = template.format(
        name=_quoted(name),
        year=f" ({year})" if year else "",
        bgg=f", BoardGameGeek id {bgg_id}" if bgg_id else "",
        base=_quoted(expansion_for or ""),
        fields=", ".join(DETAIL_ANSWERS[field] for field in DETAIL_FIELDS if field in wanted),
    )
    data, searched = await _searched_json(prompt)
    if not isinstance(data, dict):
        return FoundDetails(searched=searched, used_ai=True)
    # An image link recalled from memory is a guess, so only searched ones are used.
    image_urls = data.get("image_urls") if searched and "image_url" in wanted else None
    return FoundDetails(
        searched=searched,
        used_ai=True,
        min_players=_positive_int(data.get("min_players")) if "min_players" in wanted else None,
        max_players=_positive_int(data.get("max_players")) if "max_players" in wanted else None,
        playing_time=_positive_int(data.get("playing_time")) if "playing_time" in wanted else None,
        image_url=await _first_working_image(image_urls),
    )


def _expansion_context(base_name: str | None, expansions: Sequence[str]) -> str:
    """Tell the assistant which base game and which expansions are on the table."""
    context = ""
    if base_name:
        context += (
            f'\nIt is an expansion for "{base_name}"; answer for the two played together, '
            "and say what the expansion changes when that helps."
        )
    if expansions:
        names = ", ".join(f'"{name}"' for name in expansions)
        context += (
            f"\nThe players also own these expansions: {names}. Assume the base rules "
            "unless they mention one, and say which expansion a rule comes from."
        )
    return context


async def stream_rules_answer(
    game: Game,
    messages: list[ChatMessage],
    base_name: str | None = None,
    expansions: Sequence[str] = (),
) -> AsyncIterator[dict]:
    """Yield {"type": "text"} events as the answer streams, then one "sources" event.

    `base_name` is the base game when `game` is an expansion; `expansions` are the other
    expansions owned for it. If web search is refused for quota, a "notice" event says so
    and the answer comes from the model's own knowledge.
    """
    provider = get_provider()
    system = RULES_SYSTEM.format(
        name=game.name,
        year=f" ({game.year})" if game.year else "",
        bgg=f", BoardGameGeek id {game.bgg_id}" if game.bgg_id else "",
        context=_expansion_context(base_name, expansions),
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
