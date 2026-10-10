"""Search the BoardGameGeek ranks CSV export (id, name, year, popularity)."""

import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from ..config import settings
from ..models import Candidate

MAX_CANDIDATES = 8


class Entry(NamedTuple):
    bgg_id: int
    name: str
    year: int | None
    users_rated: int
    is_expansion: bool
    key: str  # normalized name used for matching


def is_available() -> bool:
    return settings.catalog_csv.is_file()


def normalize(text: str) -> str:
    """Lower-case, strip accents and punctuation: "Brass: Birmingham" -> "brass birmingham"."""
    decomposed = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", plain.casefold()))


def _int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def load(path: Path) -> list[Entry]:
    entries = []
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            name = (row.get("name") or "").strip()
            key = normalize(name)
            if not key or not (row.get("id") or "").isdigit():
                continue
            entries.append(
                Entry(
                    bgg_id=int(row["id"]),
                    name=name,
                    year=_int(row.get("yearpublished")) or None,  # 0 means unknown
                    users_rated=_int(row.get("usersrated")),
                    is_expansion=row.get("is_expansion") == "1",
                    key=key,
                )
            )
    return entries


@lru_cache(maxsize=1)
def _entries() -> list[Entry]:
    return load(settings.catalog_csv)


def _match_quality(key: str, wanted: str) -> int | None:
    """Lower is better; None means the name does not match."""
    if key == wanted:
        return 0
    if key.startswith(wanted + " "):
        return 1
    if f" {wanted} " in f" {key} ":
        return 2
    if key.startswith(wanted):
        return 3
    words = key.split()
    if all(any(word.startswith(part) for word in words) for part in wanted.split()):
        return 4
    return None


def search(query: str, entries: list[Entry] | None = None) -> list[Candidate]:
    """Best name matches: closest match first, then base games, then most-rated."""
    wanted = normalize(query)
    if not wanted:
        return []
    matches = []
    for entry in entries if entries is not None else _entries():
        quality = _match_quality(entry.key, wanted)
        if quality is not None:
            matches.append((quality, entry.is_expansion, -entry.users_rated, entry))
    matches.sort(key=lambda match: match[:3])
    return [
        Candidate(
            source="catalog",
            bgg_id=entry.bgg_id,
            name=entry.name,
            year=entry.year,
            is_expansion=entry.is_expansion,
        )
        for *_, entry in matches[:MAX_CANDIDATES]
    ]
