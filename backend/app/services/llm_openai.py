"""OpenAI (ChatGPT models) through the Responses API, with its web search tool."""

from collections.abc import AsyncIterator
from functools import cached_property

import openai

from ..config import settings
from ..models import ChatMessage

# Every search feeds page content back to the model as billed input tokens, and each
# extra round re-reads everything gathered so far, so searching is kept on a short leash.
SEARCH_TOOLS = [{"type": "web_search", "search_context_size": "low"}]
LOOKUP_MAX_SEARCHES = 2
CHAT_MAX_SEARCHES = 3
TIMEOUT_SECONDS = 90


def _field(item, name: str):
    """Read a field from an SDK object or a plain dict (annotations arrive as either)."""
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


class OpenAIProvider:
    label = "OpenAI"

    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    @cached_property
    def _client(self) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(
            api_key=settings.openai_api_key, timeout=TIMEOUT_SECONDS, max_retries=1
        )

    def _options(self, search: bool, max_searches: int) -> dict:
        options: dict = {"model": settings.openai_model}
        if search:
            options |= {"tools": SEARCH_TOOLS, "max_tool_calls": max_searches}
        if settings.openai_reasoning_effort:
            options["reasoning"] = {"effort": settings.openai_reasoning_effort}
        return options

    async def generate_json(self, prompt: str, *, search: bool) -> str:
        response = await self._client.responses.create(
            input=prompt, **self._options(search, LOOKUP_MAX_SEARCHES)
        )
        return response.output_text or ""

    async def stream(
        self, system: str, messages: list[ChatMessage], *, search: bool
    ) -> AsyncIterator[dict]:
        stream = await self._client.responses.create(
            instructions=system,
            input=[
                {"role": "user" if m.role == "user" else "assistant", "content": m.text}
                for m in messages
            ],
            stream=True,
            **self._options(search, CHAT_MAX_SEARCHES),
        )
        sources: dict[str, str] = {}
        async for event in stream:
            if event.type == "response.output_text.delta":
                yield {"type": "text", "text": event.delta}
            elif event.type == "response.output_text.annotation.added":
                annotation = event.annotation
                url = _field(annotation, "url")
                if _field(annotation, "type") == "url_citation" and url:
                    sources.setdefault(url, _field(annotation, "title") or url)
        if sources:
            yield {
                "type": "sources",
                "sources": [{"uri": uri, "title": title} for uri, title in sources.items()],
            }

    def quota_exceeded(self, exc: Exception) -> bool:
        return isinstance(exc, openai.RateLimitError)

    def out_of_credit(self, exc: Exception) -> bool:
        body = getattr(exc, "body", None)
        return (
            self.quota_exceeded(exc)
            and isinstance(body, dict)
            and body.get("type") == "insufficient_quota"
        )

    def overloaded(self, exc: Exception) -> bool:
        if isinstance(exc, openai.APITimeoutError):
            return True
        return isinstance(exc, openai.APIStatusError) and exc.status_code >= 500
