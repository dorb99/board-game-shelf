import asyncio
import ipaddress
import socket
import uuid
from urllib.parse import urljoin, urlparse

import httpx

from sqlmodel import Session

from ..models import Cover

MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; BoardGamesLibrary/1.0)"}


class ImageError(Exception):
    pass


def sniff_extension(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def _assert_public(url: str) -> None:
    """Reject non-http URLs and hosts that resolve to private addresses."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ImageError("Image URL must be an http(s) link.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ImageError("Could not resolve the image host.") from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise ImageError("Image URL points to a private address.")


async def fetch_image(url: str) -> tuple[bytes, str]:
    """Download an image, returning its bytes and file extension."""
    async with httpx.AsyncClient(timeout=20, headers=HEADERS) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await asyncio.to_thread(_assert_public, url)
            try:
                async with client.stream("GET", url) as response:
                    if response.is_redirect and "location" in response.headers:
                        url = urljoin(url, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        raise ImageError(f"Image host answered {response.status_code}.")
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise ImageError("Image is larger than 10 MB.")
            except httpx.HTTPError as exc:
                raise ImageError("Could not download the image.") from exc
            extension = sniff_extension(bytes(data))
            if extension is None:
                raise ImageError("That link is not a JPG, PNG, GIF or WebP image.")
            return bytes(data), extension
    raise ImageError("Too many redirects while downloading the image.")


async def is_image_url(url: str) -> bool:
    try:
        await fetch_image(url)
    except ImageError:
        return False
    return True


async def save_cover(session: Session, url: str) -> str:
    """Download a cover, add it to the session and return its name."""
    data, extension = await fetch_image(url)
    name = f"{uuid.uuid4().hex}{extension}"
    session.add(Cover(name=name, data=data))
    return name


def delete_cover(session: Session, name: str | None) -> None:
    cover = session.get(Cover, name) if name else None
    if cover:
        session.delete(cover)
