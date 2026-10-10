import pytest

from app.services import catalog, gemini, images

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
    assert gemini.extract_json(text) == expected


def test_extract_json_without_json():
    with pytest.raises(ValueError):
        gemini.extract_json("I could not find that game.")
