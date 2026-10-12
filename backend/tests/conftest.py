import os
import tempfile

# Must be set before the app is imported: settings are read at import time.
os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="boardgames-test-")
# A throwaway database, so the tests can never reach the real library.
os.environ["DATABASE_URL"] = (
    f"sqlite:///{os.environ['DATA_DIR']}/test.db?check_same_thread=false".replace("\\", "/")
)
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.db import engine
from app.main import app
from app.services import images


@pytest.fixture
def client(monkeypatch):
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

    async def fake_fetch_image(url: str) -> tuple[bytes, str]:
        if "broken" in url:
            raise images.ImageError("That link is not a JPG, PNG, GIF or WebP image.")
        return bytes.fromhex("ffd8ff") + b" cover", ".jpg"

    monkeypatch.setattr(images, "fetch_image", fake_fetch_image)
    with TestClient(app) as test_client:
        yield test_client
