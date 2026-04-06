import hashlib
from typing import Sequence

import numpy as np

from app.core.config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


class EmbeddingService:
    def __init__(self) -> None:
        self._provider = settings.embedding_provider.lower().strip()
        self._openai_client = None
        if self._provider == "openai" and settings.openai_api_key:
            if OpenAI is None:
                raise ValueError("openai package is not installed")
            self._openai_client = OpenAI(api_key=settings.openai_api_key)

    def embed_texts(self, texts: Sequence[str]) -> list[np.ndarray]:
        if self._provider == "openai":
            return self._embed_texts_openai(texts)
        return [self._embed_text_local(text) for text in texts]

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed_texts([query])[0]

    def _embed_texts_openai(self, texts: Sequence[str]) -> list[np.ndarray]:
        if self._openai_client is None:
            raise ValueError("OPENAI_API_KEY is missing while embedding_provider=openai")

        response = self._openai_client.embeddings.create(
            model=settings.openai_embedding_model,
            input=list(texts),
        )
        return [self._normalize(np.array(item.embedding, dtype=np.float32)) for item in response.data]

    def _embed_text_local(self, text: str, dimension: int = 256) -> np.ndarray:
        # Deterministic hash-based embedding for local MVP mode.
        vector = np.zeros(dimension, dtype=np.float32)
        tokens = text.lower().split()
        if not tokens:
            return self._normalize(vector)

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for i in range(0, min(dimension, len(digest) * 4)):
                byte = digest[i % len(digest)]
                sign = 1.0 if (byte % 2 == 0) else -1.0
                vector[i] += sign

        return self._normalize(vector)

    @staticmethod
    def _normalize(vector: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm
