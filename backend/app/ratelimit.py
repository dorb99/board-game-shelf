import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class RateLimiter:
    """In-memory sliding-window limit per client IP, used as a FastAPI dependency."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        hits = self.hits[key]
        while hits and now - hits[0] > self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            raise HTTPException(429, "Too many requests, try again in a few minutes.")
        hits.append(now)
