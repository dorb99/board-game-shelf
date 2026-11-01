def add_game(client, **overrides):
    payload = {
        "name": "Catan",
        "owner_name": "Dor",
        "min_players": 3,
        "max_players": 4,
        "playing_time": 90,
        "image_url": "https://example.com/catan.jpg",
    } | overrides
    return client.post("/api/games", json=payload)


def test_owner_create_and_duplicate(client):
    assert client.post("/api/owners", json={"name": "Dor"}).status_code == 201
    assert client.post("/api/owners", json={"name": " dor "}).status_code == 409
    assert [o["name"] for o in client.get("/api/owners").json()] == ["Dor"]


def test_adding_game_creates_owner_once(client):
    first = add_game(client)
    assert first.status_code == 201
    assert first.json()["image_url"].startswith("/media/covers/")
    second = add_game(client, name="Azul", owner_name="DOR")
    assert second.json()["owner_id"] == first.json()["owner_id"]
    assert len(client.get("/api/owners").json()) == 1


def test_same_game_allowed_per_owner_but_not_twice(client):
    assert add_game(client).status_code == 201
    assert add_game(client, name="catan").status_code == 409
    assert add_game(client, owner_name="Noa").status_code == 201


def test_list_games_by_owner(client):
    dor = add_game(client).json()["owner_id"]
    add_game(client, owner_name="Noa")
    add_game(client, name="Azul", owner_name="Noa")
    assert len(client.get("/api/games").json()) == 3
    assert len(client.get("/api/games", params={"owner_id": dor}).json()) == 1


def test_game_needs_an_owner(client):
    assert add_game(client, owner_name=None).status_code == 422
    assert add_game(client, owner_name=None, owner_id=999).status_code == 404


def test_bad_image_rejected_and_nothing_saved(client):
    response = add_game(client, image_url="https://example.com/broken")
    assert response.status_code == 422
    assert client.get("/api/games").json() == []
    assert client.get("/api/owners").json() == []


def test_cover_is_served_until_the_game_is_deleted(client):
    game = add_game(client).json()
    cover = client.get(game["image_url"])
    assert (cover.status_code, cover.headers["content-type"]) == (200, "image/jpeg")
    assert client.delete(f"/api/games/{game['id']}").status_code == 204
    assert client.get(game["image_url"]).status_code == 404


def test_game_without_image(client):
    assert add_game(client, image_url=None).json()["image_url"] is None


def test_update_details_and_owner(client):
    game = add_game(client).json()
    response = client.patch(
        f"/api/games/{game['id']}", json={"playing_time": 60, "owner_name": "Noa"}
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["playing_time"] == 60
    assert updated["min_players"] == 3
    assert updated["owner_id"] != game["owner_id"]

    cleared = client.patch(f"/api/games/{game['id']}", json={"playing_time": None})
    assert cleared.json()["playing_time"] is None


def test_spine_slice_defaults_and_updates(client):
    game = add_game(client).json()
    assert (game["spine_position"], game["spine_label"]) == (None, True)

    chosen = add_game(client, name="Azul", spine_position=20, spine_label=False).json()
    assert (chosen["spine_position"], chosen["spine_label"]) == (20, False)

    url = f"/api/games/{game['id']}"
    updated = client.patch(url, json={"spine_position": 80, "spine_label": False}).json()
    assert (updated["spine_position"], updated["spine_label"]) == (80, False)
    # Other edits leave the slice alone
    untouched = client.patch(url, json={"playing_time": 30}).json()
    assert (untouched["spine_position"], untouched["spine_label"]) == (80, False)
    assert client.patch(url, json={"spine_position": 101}).status_code == 422


def test_existing_database_gets_new_columns(client):
    from sqlalchemy import inspect, text

    from app.db import create_tables, engine

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE game DROP COLUMN spine_position"))
        connection.execute(text("ALTER TABLE game DROP COLUMN spine_label"))
    create_tables()
    columns = {column["name"] for column in inspect(engine).get_columns("game")}
    assert {"spine_position", "spine_label"} <= columns
    assert add_game(client).json()["spine_label"] is True


def test_update_rejects_inverted_player_range(client):
    game = add_game(client).json()
    response = client.patch(f"/api/games/{game['id']}", json={"min_players": 6})
    assert response.status_code == 422


def test_cannot_move_game_to_owner_who_has_it(client):
    game = add_game(client).json()
    add_game(client, owner_name="Noa")
    response = client.patch(f"/api/games/{game['id']}", json={"owner_name": "Noa"})
    assert response.status_code == 409


def test_delete_game(client):
    game = add_game(client).json()
    assert client.delete(f"/api/games/{game['id']}").status_code == 204
    assert client.get("/api/games").json() == []
    assert client.delete(f"/api/games/{game['id']}").status_code == 404


def test_lookup_without_catalog_or_key_reports_warnings(client):
    body = client.get("/api/lookup", params={"q": "catan"}).json()
    assert body["candidates"] == []
    assert len(body["warnings"]) == 2


def test_lookup_uses_catalog_before_llm(client, monkeypatch):
    from app.models import Candidate
    from app.services import catalog, llm

    async def must_not_run(query, expansion_for=None):
        raise AssertionError("The LLM must not be asked when the catalog has a match")

    found = [Candidate(source="catalog", bgg_id=13, name="CATAN", year=1995)]
    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(
        catalog, "search", lambda query, **_: found if query == "catan" else []
    )
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", must_not_run)
    body = client.get("/api/lookup", params={"q": " catan "}).json()
    assert [c["bgg_id"] for c in body["candidates"]] == [13]
    assert body["warnings"] == []


def test_lookup_falls_back_to_llm_when_not_in_catalog(client, monkeypatch):
    from app.models import Candidate
    from app.services import catalog, llm

    async def fake_lookup(query, expansion_for=None):
        return [Candidate(source="web", name="Brand New Game")], False

    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query, **_: [])
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", fake_lookup)
    body = client.get("/api/lookup", params={"q": "brand new game"}).json()
    assert [c["source"] for c in body["candidates"]] == ["web"]
    assert body["warnings"] == [llm.not_searched_message()]  # search was refused, so say so


def test_expansion_lookups_name_the_base_game(client, monkeypatch):
    from app.models import Candidate, FoundDetails
    from app.services import catalog, llm

    asked = []

    def fake_search(query, expansions_first=False):
        asked.append(("catalog", expansions_first))
        return []

    async def fake_lookup(query, expansion_for=None):
        asked.append(("web", expansion_for))
        return [Candidate(source="web", name="Seafarers", is_expansion=True)], True

    async def fake_fetch_details(name, year, bgg_id, expansion_for=None, **_):
        asked.append(("details", expansion_for))
        return FoundDetails(min_players=5, max_players=6)

    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", fake_search)
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", fake_lookup)
    monkeypatch.setattr(llm, "fetch_details", fake_fetch_details)
    params = {"q": "seafarers", "expansion_for": " Catan "}
    assert client.get("/api/lookup", params=params).status_code == 200
    params = {"name": "Seafarers", "expansion_for": "Catan"}
    assert client.get("/api/lookup/details", params=params).json()["max_players"] == 6
    assert asked == [("catalog", True), ("web", "Catan"), ("details", "Catan")]


def test_chat_requires_llm_key(client):
    game = add_game(client).json()
    response = client.post(
        f"/api/games/{game['id']}/chat",
        json={"messages": [{"role": "user", "text": "How do I win?"}]},
    )
    assert response.status_code == 503


def test_details_lookup_requires_llm_key(client):
    assert client.get("/api/lookup/details", params={"name": "Catan"}).status_code == 503


def test_details_lookup_uses_llm(client, monkeypatch):
    from app.models import FoundDetails
    from app.services import llm

    async def fake_fetch_details(name, year, bgg_id, expansion_for=None, **_):
        assert (name, year, bgg_id, expansion_for) == ("Catan", 1995, 13, None)
        return FoundDetails(min_players=3, max_players=4, image_url="https://example.com/c.jpg")

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "fetch_details", fake_fetch_details)
    params = {"name": " Catan ", "year": 1995, "bgg_id": 13}
    body = client.get("/api/lookup/details", params=params).json()
    assert body == {
        "min_players": 3,
        "max_players": 4,
        "playing_time": None,
        "image_url": "https://example.com/c.jpg",
        "searched": True,
        "used_ai": True,
    }


def test_create_saves_exactly_what_was_reviewed(client, monkeypatch):
    from app.services import llm

    async def must_not_run(name, year, bgg_id, expansion_for=None):
        raise AssertionError("create must not look details up on its own")

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "fetch_details", must_not_run)
    game = add_game(client, playing_time=None).json()
    assert game["playing_time"] is None
    assert "description" not in game


def test_expansion_takes_its_base_games_owner(client):
    base = add_game(client).json()
    expansion = add_game(client, name="Seafarers", owner_name="Noa", parent_id=base["id"])
    assert expansion.status_code == 201
    assert expansion.json()["parent_id"] == base["id"]
    assert expansion.json()["owner_id"] == base["owner_id"]
    assert len(client.get("/api/owners").json()) == 1


def test_expansions_go_one_level_deep(client):
    base = add_game(client).json()
    expansion = add_game(client, name="Seafarers", parent_id=base["id"]).json()
    assert add_game(client, name="Pirates", parent_id=expansion["id"]).status_code == 422
    assert add_game(client, name="Pirates", parent_id=999).status_code == 404
    patch = lambda game, **changes: client.patch(f"/api/games/{game['id']}", json=changes)
    assert patch(base, parent_id=base["id"]).status_code == 422
    other = add_game(client, name="Azul").json()
    assert patch(base, parent_id=other["id"]).status_code == 422  # base has expansions


def test_linking_and_unlinking_an_expansion(client):
    base = add_game(client).json()
    loose = add_game(client, name="Seafarers", owner_name="Noa").json()
    linked = client.patch(f"/api/games/{loose['id']}", json={"parent_id": base["id"]}).json()
    assert (linked["parent_id"], linked["owner_id"]) == (base["id"], base["owner_id"])
    noa = client.post("/api/owners", json={"name": "Noa2"}).json()
    moved = client.patch(f"/api/games/{loose['id']}", json={"owner_id": noa["id"]})
    assert moved.status_code == 422  # an expansion follows its base game
    freed = client.patch(f"/api/games/{loose['id']}", json={"parent_id": None}).json()
    assert freed["parent_id"] is None


def test_expansions_move_and_go_with_their_base_game(client):
    base = add_game(client).json()
    expansion = add_game(client, name="Seafarers", parent_id=base["id"]).json()
    moved = client.patch(f"/api/games/{base['id']}", json={"owner_name": "Noa"}).json()
    games = {game["id"]: game for game in client.get("/api/games").json()}
    assert games[expansion["id"]]["owner_id"] == moved["owner_id"]

    assert client.delete(f"/api/games/{base['id']}").status_code == 204
    assert client.get("/api/games").json() == []
    assert client.get(expansion["image_url"]).status_code == 404


def use_bgg(monkeypatch, things=None, search=None):
    """Turn the BGG API on with canned answers; returns the list of calls made to it."""
    from app.services import bgg

    calls = []

    async def fake_things(ids):
        calls.append(("thing", list(ids)))
        return {i: t for i, t in (things or {}).items() if i in ids}

    async def fake_search(query, expansions_first=False):
        calls.append(("search", query))
        return [t.candidate() for t in search or []]

    monkeypatch.setattr(bgg, "is_configured", lambda: True)
    monkeypatch.setattr(bgg, "things", fake_things)
    monkeypatch.setattr(bgg, "search", fake_search)
    return calls


def bgg_thing(**overrides):
    from app.services.bgg import Thing

    fields = dict(bgg_id=13, name="CATAN", year=1995, is_expansion=False, min_players=3,
                  max_players=4, playing_time=90, image_url="https://cf.geekdo-images.com/c.jpg",
                  thumbnail_url="https://cf.geekdo-images.com/t.jpg")
    return Thing(**(fields | overrides))


def test_lookup_fills_catalog_matches_in_from_bgg(client, monkeypatch):
    from app.models import Candidate
    from app.services import catalog

    found = [Candidate(source="catalog", bgg_id=13, name="CATAN", year=1995)]
    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query, **_: found)
    calls = use_bgg(monkeypatch, things={13: bgg_thing()})
    (catan,) = client.get("/api/lookup", params={"q": "catan"}).json()["candidates"]
    assert (catan["source"], catan["max_players"], catan["playing_time"]) == ("bgg", 4, 90)
    assert catan["image_url"] == "https://cf.geekdo-images.com/c.jpg"
    assert calls == [("thing", [13])]


def test_lookup_searches_bgg_before_the_llm(client, monkeypatch):
    from app.services import catalog, llm

    async def must_not_run(query, expansion_for=None):
        raise AssertionError("The LLM must not be asked when BGG finds the game")

    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query, **_: [])
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", must_not_run)
    calls = use_bgg(monkeypatch, search=[bgg_thing(bgg_id=400, name="Brand New Game")])
    body = client.get("/api/lookup", params={"q": "brand new game"}).json()
    assert [(c["source"], c["bgg_id"]) for c in body["candidates"]] == [("bgg", 400)]
    assert calls == [("search", "brand new game")]


def test_lookup_goes_on_to_the_llm_when_bgg_fails(client, monkeypatch):
    from app.models import Candidate
    from app.services import bgg, catalog, llm

    async def broken(*args, **kwargs):
        raise bgg.BggError("BoardGameGeek answered 503.")

    async def fake_lookup(query, expansion_for=None):
        return [Candidate(source="web", name="Brand New Game")], True

    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query, **_: [])
    monkeypatch.setattr(bgg, "is_configured", lambda: True)
    monkeypatch.setattr(bgg, "search", broken)
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", fake_lookup)
    body = client.get("/api/lookup", params={"q": "brand new game"}).json()
    assert [c["source"] for c in body["candidates"]] == ["web"]


def test_details_from_bgg_need_no_llm(client, monkeypatch):
    use_bgg(monkeypatch, things={13: bgg_thing()})
    body = client.get("/api/lookup/details", params={"name": "Catan", "bgg_id": 13}).json()
    assert body == {
        "min_players": 3,
        "max_players": 4,
        "playing_time": 90,
        "image_url": "https://cf.geekdo-images.com/c.jpg",
        "searched": True,
        "used_ai": False,
    }


def test_details_ask_the_llm_only_for_what_bgg_lacks(client, monkeypatch):
    from app.models import FoundDetails
    from app.services import llm

    asked = []

    async def fake_fetch_details(name, year, bgg_id, expansion_for=None, wanted=()):
        asked.append(list(wanted))
        return FoundDetails(min_players=9, playing_time=45, image_url="https://e.com/x.jpg")

    use_bgg(monkeypatch, things={13: bgg_thing(playing_time=None, image_url=None)})
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "fetch_details", fake_fetch_details)
    params = {"name": "Catan", "bgg_id": 13, "want": ["min_players", "playing_time"]}
    body = client.get("/api/lookup/details", params=params).json()
    assert asked == [["playing_time"]]  # the cover was not wanted, and BGG had the players
    assert (body["min_players"], body["playing_time"], body["image_url"]) == (3, 45, None)
    assert body["used_ai"] is True


def test_details_keep_what_bgg_found_when_the_llm_fails(client, monkeypatch):
    from app.services import llm

    async def broken(*args, **kwargs):
        raise RuntimeError("down")

    use_bgg(monkeypatch, things={13: bgg_thing(image_url=None)})
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "fetch_details", broken)
    body = client.get("/api/lookup/details", params={"name": "Catan", "bgg_id": 13}).json()
    assert (body["max_players"], body["image_url"]) == (4, None)
