"""Google Gemini, with Google Search grounding for web search."""

from collections.abc import AsyncIterator
from functools import cached_property

from google import genai
from google.genai import errors, types

from ..config import settings
from ..models import ChatMessage

SEARCH_TOOL = types.Tool(google_search=types.GoogleSearch())


class GeminiProvider:
    label = "Gemini"

    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    @cached_property
    def _client(self) -> genai.Client:
        # Kept for the provider's lifetime: a Client closes its connections when
        # garbage-collected, which breaks any call still using them.
        return genai.Client(api_key=settings.gemini_api_key)

    def _config(self, search: bool, **options) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(tools=[SEARCH_TOOL] if search else None, **options)

    async def generate_json(self, prompt: str, *, search: bool) -> str:
        response = await self._client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            # JSON mode cannot be combined with the search tool, so it is used without it.
            config=self._config(
                search,
                temperature=0,
                response_mime_type=None if search else "application/json",
            ),
        )
        return response.text or ""

    async def stream(
        self, system: str, messages: list[ChatMessage], *, search: bool
    ) -> AsyncIterator[dict]:
        contents = [
            types.Content(
                role="user" if m.role == "user" else "model", parts=[types.Part(text=m.text)]
            )
            for m in messages
        ]
        stream = await self._client.aio.models.generate_content_stream(
            model=settings.gemini_model,
            contents=contents,
            config=self._config(search, system_instruction=system, temperature=0.2),
        )
        sources: dict[str, str] = {}
        async for chunk in stream:
            if chunk.text:
                yield {"type": "text", "text": chunk.text}
            for candidate in chunk.candidates or []:
                metadata = candidate.grounding_metadata
                for grounding in (metadata.grounding_chunks if metadata else None) or []:
                    if grounding.web and grounding.web.uri:
                        sources.setdefault(
                            grounding.web.uri, grounding.web.title or grounding.web.uri
                        )
        if sources:
            yield {
                "type": "sources",
                "sources": [{"uri": uri, "title": title} for uri, title in sources.items()],
            }

    def quota_exceeded(self, exc: Exception) -> bool:
        return isinstance(exc, errors.APIError) and exc.code == 429

    def out_of_credit(self, exc: Exception) -> bool:
        return False  # Gemini reports every quota problem the same way

    def overloaded(self, exc: Exception) -> bool:
        return isinstance(exc, errors.APIError) and exc.code == 503
