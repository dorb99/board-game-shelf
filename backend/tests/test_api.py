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
    assert first.json()["image_url"] == "/media/covers/cover.jpg"
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

    async def must_not_run(query):
        raise AssertionError("The LLM must not be asked when the catalog has a match")

    found = [Candidate(source="catalog", bgg_id=13, name="CATAN", year=1995)]
    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query: found if query == "catan" else [])
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", must_not_run)
    body = client.get("/api/lookup", params={"q": " catan "}).json()
    assert [c["bgg_id"] for c in body["candidates"]] == [13]
    assert body["warnings"] == []


def test_lookup_falls_back_to_llm_when_not_in_catalog(client, monkeypatch):
    from app.models import Candidate
    from app.services import catalog, llm

    async def fake_lookup(query):
        return [Candidate(source="web", name="Brand New Game")], False

    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query: [])
    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "lookup_candidates", fake_lookup)
    body = client.get("/api/lookup", params={"q": "brand new game"}).json()
    assert [c["source"] for c in body["candidates"]] == ["web"]
    assert body["warnings"] == [llm.not_searched_message()]  # search was refused, so say so


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

    async def fake_fetch_details(name, year, bgg_id):
        assert (name, year, bgg_id) == ("Catan", 1995, 13)
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
    }


def test_create_saves_exactly_what_was_reviewed(client, monkeypatch):
    from app.services import llm

    async def must_not_run(name, year, bgg_id):
        raise AssertionError("create must not look details up on its own")

    monkeypatch.setattr(llm, "is_configured", lambda: True)
    monkeypatch.setattr(llm, "fetch_details", must_not_run)
    game = add_game(client, playing_time=None).json()
    assert game["playing_time"] is None
    assert "description" not in game
