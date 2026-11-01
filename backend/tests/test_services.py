import asyncio
import pytest

from app.models import ChatMessage, Game
from app.services import catalog, images, llm

CATALOG_CSV = """id,name,yearpublished,rank,bayesaverage,average,usersrated,is_expansion
13,CATAN,1995,600,6.9,7.1,130000,0
926,"CATAN: Cities & Knights",1998,0,0,7.0,30000,1
27710,"Catan Dice Game",2007,9000,5.6,5.7,9000,0
278,"Catan Card Game",1996,3000,6.4,6.6,12000,0
172,"Die Siedler von Catan: Das Buch",2000,0,0,6.5,300,0
230802,Azul,2017,80,7.6,7.7,95000,0
199,"Pokémon Trading Card Game",1996,0,0,6.0,5000,0
5,Unknown Year Game,0,0,0,0,0,0
"""


@pytest.fixture
def entries(tmp_path):
    path = tmp_path / "ranks.csv"
    path.write_text(CATALOG_CSV, encoding="utf-8")
    return catalog.load(path)


def test_catalog_load(entries):
    assert len(entries) == 8
    catan = entries[0]
    assert (catan.bgg_id, catan.name, catan.year, catan.users_rated) == (13, "CATAN", 1995, 130000)
    assert entries[1].is_expansion and not catan.is_expansion
    assert entries[-1].year is None  # the export uses 0 for an unknown year


def test_catalog_search_orders_by_match_then_base_game_then_popularity(entries):
    names = [c.name for c in catalog.search("catan", entries)]
    assert names == [
        "CATAN",  # exact
        "Catan Card Game",  # starts with the word; base games by popularity
        "Catan Dice Game",
        "CATAN: Cities & Knights",  # expansions after base games
        "Die Siedler von Catan: Das Buch",  # word inside the name
    ]


def test_catalog_search_for_an_expansion_puts_expansions_first(entries):
    names = [c.name for c in catalog.search("catan", entries, expansions_first=True)]
    assert names[:2] == ["CATAN: Cities & Knights", "CATAN"]


def test_catalog_search_candidate_fields(entries):
    (azul,) = catalog.search("  AZUL ", entries)
    assert (azul.source, azul.bgg_id, azul.year, azul.image_url) == ("catalog", 230802, 2017, None)


def test_catalog_search_ignores_accents_punctuation_and_allows_partial_words(entries):
    assert [c.bgg_id for c in catalog.search("pokemon card", entries)] == [199]
    assert [c.bgg_id for c in catalog.search("cities knights", entries)] == [926]
    assert [c.bgg_id for c in catalog.search("azu", entries)] == [230802]
    assert catalog.search("wingspan", entries) == []
    assert catalog.search("!!!", entries) == []


@pytest.mark.parametrize(
    "data, expected",
    [
        (b"\xff\xd8\xff\xe0rest", ".jpg"),
        (b"\x89PNG\r\n\x1a\nrest", ".png"),
        (b"GIF89arest", ".gif"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", ".webp"),
        (b"<html>not an image</html>", None),
        (b"", None),
    ],
)
def test_sniff_extension(data, expected):
    assert images.sniff_extension(data) == expected


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/a.jpg", "file:///etc/passwd", "http://127.0.0.1/a.jpg",
     "http://localhost/a.jpg", "http://192.168.1.10/a.jpg", "http://169.254.169.254/x"],
)
def test_private_and_non_http_urls_rejected(url):
    with pytest.raises(images.ImageError):
        images._assert_public(url)


@pytest.mark.parametrize(
    "text, expected",
    [
        ('{"min_players": 2}', {"min_players": 2}),
        ('Here you go:\n```json\n[{"name": "Azul"}]\n```\nEnjoy', [{"name": "Azul"}]),
        ('Sure. {"a": [1, 2]} done', {"a": [1, 2]}),
    ],
)
def test_extract_json(text, expected):
    assert llm.extract_json(text) == expected


class QuotaError(Exception):
    pass


class FakeProvider:
    """Stands in for an LLM service; can refuse any call that asks for web search."""

    label = "FakeAI"

    def __init__(self, reply: str, search_allowed: bool = True):
        self.reply = reply
        self.search_allowed = search_allowed
        self.calls: list[bool] = []  # the `search` flag of each call

    def is_configured(self):
        return True

    def _check(self, search):
        self.calls.append(search)
        if search and not self.search_allowed:
            raise QuotaError()

    async def generate_json(self, prompt, *, search):
        self._check(search)
        return self.reply

    async def stream(self, system, messages, *, search):
        self._check(search)
        yield {"type": "text", "text": self.reply}
        if search:
            yield {"type": "sources", "sources": [{"uri": "https://rules.example", "title": "Rules"}]}

    def quota_exceeded(self, exc):
        return isinstance(exc, QuotaError)

    def out_of_credit(self, exc):
        return False

    def overloaded(self, exc):
        return False


def use_provider(monkeypatch, provider: FakeProvider) -> FakeProvider:
    monkeypatch.setattr(llm, "get_provider", lambda: provider)
    return provider


DETAILS_REPLY = (
    '{"min_players": 1, "max_players": 5, "playing_time": 70,'
    ' "image_urls": ["https://example.com/cover.jpg"]}'
)


def ask_rules():
    async def collect():
        game = Game(name="Wingspan", owner_id=1)
        question = [ChatMessage(role="user", text="Starting food?")]
        return [event async for event in llm.stream_rules_answer(game, question)]

    return asyncio.run(collect())


def test_provider_is_chosen_by_setting(monkeypatch):
    from app.config import settings
    from app.services.llm_gemini import GeminiProvider
    from app.services.llm_openai import OpenAIProvider

    for name, expected in (("gemini", GeminiProvider), ("openai", OpenAIProvider)):
        monkeypatch.setattr(settings, "llm_provider", name)
        llm.get_provider.cache_clear()
        assert isinstance(llm.get_provider(), expected)
    llm.get_provider.cache_clear()


def test_openai_out_of_credit_is_told_apart_from_rate_limits(monkeypatch):
    import httpx
    import openai

    from app.services.llm_openai import OpenAIProvider

    def rate_limit_error(error_type):
        response = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com"))
        return openai.RateLimitError("x", response=response, body={"type": error_type})

    provider = OpenAIProvider()
    monkeypatch.setattr(llm, "get_provider", lambda: provider)
    no_credit = rate_limit_error("insufficient_quota")
    assert provider.out_of_credit(no_credit)
    assert "no credit" in llm.error_message(no_credit, "generic")
    too_fast = rate_limit_error("requests")
    assert not provider.out_of_credit(too_fast)
    assert "quota exceeded" in llm.error_message(too_fast, "generic")


def test_openai_requests_keep_web_search_on_a_short_leash(monkeypatch):
    from types import SimpleNamespace

    from app.config import settings
    from app.services import llm_openai

    sent = []

    async def create(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(output_text="{}")

    provider = llm_openai.OpenAIProvider()
    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    monkeypatch.setattr(settings, "openai_reasoning_effort", "low")
    asyncio.run(provider.generate_json("find it", search=True))
    asyncio.run(provider.generate_json("find it", search=False))

    searched, unsearched = sent
    assert searched["max_tool_calls"] == llm_openai.LOOKUP_MAX_SEARCHES
    assert searched["tools"] == [{"type": "web_search", "search_context_size": "low"}]
    assert searched["reasoning"] == {"effort": "low"}
    assert "tools" not in unsearched and "max_tool_calls" not in unsearched

    monkeypatch.setattr(settings, "openai_reasoning_effort", "")
    asyncio.run(provider.generate_json("find it", search=True))
    assert "reasoning" not in sent[-1]


def test_provider_needs_its_own_key(monkeypatch):
    from app.config import settings
    from app.services.llm_openai import OpenAIProvider

    monkeypatch.setattr(settings, "gemini_api_key", "a-gemini-key")
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert OpenAIProvider().is_configured() is False
    monkeypatch.setattr(settings, "openai_api_key", "an-openai-key")
    assert OpenAIProvider().is_configured() is True


def test_error_messages_name_the_provider(monkeypatch):
    use_provider(monkeypatch, FakeProvider(""))
    assert llm.error_message(QuotaError(), "generic").startswith("FakeAI quota exceeded")
    assert llm.error_message(ValueError("x"), "generic") == "generic"
    assert "unusable answer" in llm.error_message(llm.NoAnswer(), "generic")
    assert llm.not_configured_message().startswith("FakeAI API key")


def test_details_use_web_search(monkeypatch):
    async def image_ok(url):
        return True

    monkeypatch.setattr(images, "is_image_url", image_ok)
    provider = use_provider(monkeypatch, FakeProvider(DETAILS_REPLY))
    found = asyncio.run(llm.fetch_details("Wingspan", 2019, 266192))
    assert provider.calls == [True]
    assert (found.min_players, found.max_players, found.playing_time) == (1, 5, 70)
    assert (found.searched, found.image_url) == (True, "https://example.com/cover.jpg")


def test_expansion_details_ask_for_players_with_the_expansion(monkeypatch):
    provider = use_provider(monkeypatch, FakeProvider(DETAILS_REPLY))
    prompts = []
    original = provider.generate_json

    async def record(prompt, *, search):
        prompts.append(prompt)
        return await original(prompt, search=search)

    monkeypatch.setattr(provider, "generate_json", record)
    monkeypatch.setattr(images, "is_image_url", lambda url: asyncio.sleep(0, True))
    asyncio.run(llm.fetch_details("Seafarers", None, None, expansion_for="Catan"))
    prompt = " ".join(prompts[0].split())
    assert '"Seafarers", an expansion for the board game "Catan"' in prompt
    assert "supports once this expansion is added" in prompt


def test_details_fall_back_to_memory_when_search_is_refused(monkeypatch):
    provider = use_provider(monkeypatch, FakeProvider(DETAILS_REPLY, search_allowed=False))
    found = asyncio.run(llm.fetch_details("Wingspan", 2019, 266192))
    assert provider.calls == [True, False]  # tried search first, then without
    assert (found.min_players, found.max_players, found.playing_time) == (1, 5, 70)
    assert found.searched is False
    assert found.image_url is None  # a remembered link is a guess, so it is dropped


def test_rules_chat_streams_text_then_sources(monkeypatch):
    use_provider(monkeypatch, FakeProvider("Each player starts with 5 food."))
    assert [event["type"] for event in ask_rules()] == ["text", "sources"]


def test_rules_chat_falls_back_with_a_notice(monkeypatch):
    use_provider(monkeypatch, FakeProvider("Each player starts with 5 food.", search_allowed=False))
    assert ask_rules() == [
        {"type": "notice", "message": llm.not_searched_message()},
        {"type": "text", "text": "Each player starts with 5 food."},
    ]


def test_extract_json_without_json():
    with pytest.raises(ValueError):
        llm.extract_json("I could not find that game.")


def test_rules_prompt_names_the_base_game_and_owned_expansions():
    context = llm._expansion_context("Catan", ["Seafarers", "Cities & Knights"])
    assert '"Catan"' in context
    assert '"Seafarers", "Cities & Knights"' in context
    assert llm._expansion_context(None, []) == ""


THING_XML = """<?xml version="1.0" encoding="utf-8"?>
<items termsofuse="https://boardgamegeek.com/xmlapi/termsofuse">
  <item type="boardgame" id="13">
    <thumbnail>https://cf.geekdo-images.com/catan_thumb.jpg</thumbnail>
    <image>https://cf.geekdo-images.com/catan.jpg</image>
    <name type="alternate" sortindex="1" value="Die Siedler von Catan" />
    <name type="primary" sortindex="1" value="CATAN" />
    <yearpublished value="1995" />
    <minplayers value="3" />
    <maxplayers value="4" />
    <playingtime value="120" />
    <minplaytime value="60" />
    <maxplaytime value="120" />
  </item>
  <item type="boardgameexpansion" id="926">
    <name type="primary" sortindex="1" value="CATAN: Cities &amp; Knights" />
    <yearpublished value="1998" />
    <minplayers value="3" />
    <maxplayers value="4" />
    <playingtime value="0" />
    <maxplaytime value="90" />
    <link type="boardgameexpansion" id="13" value="CATAN" inbound="true" />
  </item>
</items>"""

SEARCH_XML = """<?xml version="1.0" encoding="utf-8"?>
<items total="3" termsofuse="https://boardgamegeek.com/xmlapi/termsofuse">
  <item type="boardgame" id="926"><name type="primary" value="CATAN: Cities &amp; Knights"/></item>
  <item type="boardgame" id="99"><name type="alternate" value="Siedler"/></item>
  <item type="boardgame" id="13"><name type="primary" value="CATAN"/></item>
  <item type="boardgameexpansion" id="926"><name type="primary" value="CATAN: Cities &amp; Knights"/></item>
</items>"""


@pytest.fixture
def fake_bgg(monkeypatch):
    """Answers BGG requests from the canned XML and records each one."""
    from app.services import bgg

    calls = []

    async def fake_get(path, params):
        calls.append((path, params))
        return SEARCH_XML if path == "search" else THING_XML

    monkeypatch.setattr(bgg, "_get", fake_get)
    monkeypatch.setattr(bgg, "_cache", {})
    return calls


def test_bgg_things_are_parsed():
    from app.services import bgg

    catan, cities = bgg.parse_things(THING_XML)
    assert catan == bgg.Thing(
        bgg_id=13, name="CATAN", year=1995, is_expansion=False, min_players=3, max_players=4,
        playing_time=120, image_url="https://cf.geekdo-images.com/catan.jpg",
        thumbnail_url="https://cf.geekdo-images.com/catan_thumb.jpg",
    )
    assert cities.is_expansion and cities.name == "CATAN: Cities & Knights"
    assert cities.playing_time == 90  # 0 means unknown, so the longest play time stands in
    assert (cities.image_url, cities.thumbnail_url) == (None, None)


def test_bgg_details_are_fetched_once_in_batches(fake_bgg):
    from app.services import bgg

    found = asyncio.run(bgg.things([13, 926, 13]))
    assert set(found) == {13, 926}
    assert fake_bgg == [("thing", {"id": "13,926"})]
    asyncio.run(bgg.things([926, 13]))
    assert len(fake_bgg) == 1  # cached


def test_bgg_enrich_fills_in_catalog_matches(fake_bgg):
    from app.models import Candidate
    from app.services import bgg

    matches = [Candidate(source="catalog", bgg_id=13, name="CATAN"),
               Candidate(source="catalog", bgg_id=5, name="Not on BGG")]
    catan, other = asyncio.run(bgg.enrich(matches))
    assert (catan.source, catan.max_players, catan.image_url) == (
        "bgg", 4, "https://cf.geekdo-images.com/catan.jpg")
    assert other == matches[1]


def test_bgg_search_puts_the_closest_base_game_first(fake_bgg):
    from app.services import bgg

    found = asyncio.run(bgg.search("catan"))
    assert [c.bgg_id for c in found] == [13, 926]  # exact name first; 99 is not in the details
    assert all(c.source == "bgg" for c in found)
    found = asyncio.run(bgg.search("catan", expansions_first=True))
    assert [c.bgg_id for c in found] == [926, 13]
    assert fake_bgg[0] == ("search", {"query": "catan", "type": "boardgame,boardgameexpansion"})


def test_bgg_is_retried_while_busy(monkeypatch):
    import httpx

    from app.config import settings
    from app.services import bgg

    replies = [httpx.Response(202), httpx.Response(503), httpx.Response(200, text=THING_XML)]
    sent = []

    def handler(request):
        sent.append(request)
        return replies.pop(0)

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    monkeypatch.setattr(bgg, "RETRY_DELAYS", (0, 0))
    monkeypatch.setattr(bgg, "MIN_SPACING", 0)
    monkeypatch.setattr(settings, "bgg_api_token", "secret")
    assert asyncio.run(bgg._get("thing", {"id": "13"})) == THING_XML
    assert len(sent) == 3
    assert sent[0].headers["Authorization"] == "Bearer secret"
    assert str(sent[0].url) == "https://boardgamegeek.com/xmlapi2/thing?id=13"

    replies[:] = [httpx.Response(401)]
    with pytest.raises(bgg.BggError):
        asyncio.run(bgg._get("thing", {"id": "13"}))


def test_details_ask_the_ai_only_for_what_is_wanted(monkeypatch):
    provider = use_provider(monkeypatch, FakeProvider(DETAILS_REPLY))
    prompts = []
    original = provider.generate_json

    async def record(prompt, *, search):
        prompts.append(prompt)
        return await original(prompt, search=search)

    monkeypatch.setattr(provider, "generate_json", record)
    found = asyncio.run(llm.fetch_details("Wingspan", 2019, 266192, wanted=["playing_time"]))
    assert '{"playing_time": int|null}' in prompts[0]
    assert "image_urls" not in prompts[0] and "min_players" not in prompts[0]
    assert (found.playing_time, found.min_players, found.image_url) == (70, None, None)
    assert found.used_ai
