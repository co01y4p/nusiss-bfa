import hashlib
import math
import re
from typing import Protocol

import httpx

from app.llm.retry import with_transient_retries


class EmbeddingProvider(Protocol):
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class FakeEmbeddings:
    """Deterministic local embedding provider for tests and development without external API."""

    def __init__(self, dim: int = 1536) -> None:
        self.dim = dim

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vectorize(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vectorize(text)

    def _vectorize(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        words = re.findall(r"\w+", text.lower())

        if not words:
            # Baseline deterministic hash
            h = hashlib.sha256(text.encode("utf-8")).digest()
            for i in range(min(self.dim, len(h) * 4)):
                vector[i] = float(h[i % len(h)]) / 255.0
        else:
            # Bag-of-words hash projection so shared words produce positive cosine similarity
            for word in words:
                word_hash = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
                idx = word_hash % self.dim
                sign = 1.0 if (word_hash >> 1) % 2 == 0 else -1.0
                vector[idx] += sign

        # Normalize to unit vector
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0.0:
            vector = [v / norm for v in vector]
        else:
            vector[0] = 1.0

        return vector


class OpenAICompatibleEmbeddings:
    """Embeddings provider using OpenAI-compatible /embeddings API (OpenAI, OpenRouter, Gemini)."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = "text-embedding-3-small",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async def send() -> list[list[float]]:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model, "input": texts},
                )
                response.raise_for_status()
                data = response.json().get("data", [])
                # Ensure ordered by index
                data.sort(key=lambda x: x.get("index", 0))
                return [item["embedding"] for item in data]

        return await with_transient_retries(send, retries=2)

    async def embed_query(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        if not results:
            raise RuntimeError("Embeddings provider returned empty result for query")
        return results[0]
