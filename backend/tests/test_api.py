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


def test_lookup_uses_catalog_before_gemini(client, monkeypatch):
    from app.models import Candidate
    from app.services import catalog, gemini

    async def must_not_run(query):
        raise AssertionError("Gemini must not be asked when the catalog has a match")

    found = [Candidate(source="catalog", bgg_id=13, name="CATAN", year=1995)]
    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query: found if query == "catan" else [])
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "lookup_candidates", must_not_run)
    body = client.get("/api/lookup", params={"q": " catan "}).json()
    assert [c["bgg_id"] for c in body["candidates"]] == [13]
    assert body["warnings"] == []


def test_lookup_falls_back_to_gemini_when_not_in_catalog(client, monkeypatch):
    from app.models import Candidate
    from app.services import catalog, gemini

    async def fake_lookup(query):
        return [Candidate(source="gemini", name="Brand New Game")]

    monkeypatch.setattr(catalog, "is_available", lambda: True)
    monkeypatch.setattr(catalog, "search", lambda query: [])
    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "lookup_candidates", fake_lookup)
    body = client.get("/api/lookup", params={"q": "brand new game"}).json()
    assert [c["source"] for c in body["candidates"]] == ["gemini"]


def test_chat_requires_gemini_key(client):
    game = add_game(client).json()
    response = client.post(
        f"/api/games/{game['id']}/chat",
        json={"messages": [{"role": "user", "text": "How do I win?"}]},
    )
    assert response.status_code == 503


def test_details_lookup_requires_gemini_key(client):
    assert client.get("/api/lookup/details", params={"name": "Catan"}).status_code == 503


def test_details_lookup_uses_gemini(client, monkeypatch):
    from app.models import FoundDetails
    from app.services import gemini

    async def fake_fetch_details(name, year, bgg_id):
        assert (name, year, bgg_id) == ("Catan", 1995, 13)
        return FoundDetails(min_players=3, max_players=4, image_url="https://example.com/c.jpg")

    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "fetch_details", fake_fetch_details)
    params = {"name": " Catan ", "year": 1995, "bgg_id": 13}
    body = client.get("/api/lookup/details", params=params).json()
    assert body == {
        "min_players": 3,
        "max_players": 4,
        "playing_time": None,
        "description": None,
        "image_url": "https://example.com/c.jpg",
    }


def test_create_saves_exactly_what_was_reviewed(client, monkeypatch):
    from app.services import gemini

    async def must_not_run(name, year, bgg_id):
        raise AssertionError("create must not look details up on its own")

    monkeypatch.setattr(gemini, "is_configured", lambda: True)
    monkeypatch.setattr(gemini, "fetch_details", must_not_run)
    game = add_game(client, playing_time=None, description="Reviewed text").json()
    assert game["playing_time"] is None
    assert game["description"] == "Reviewed text"
