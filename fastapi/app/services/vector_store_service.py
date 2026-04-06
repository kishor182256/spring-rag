from dataclasses import dataclass

import numpy as np

from app.services.chunking_service import ChunkRecord


@dataclass
class VectorMatch:
    score: float
    chunk: ChunkRecord


class InMemoryVectorStore:
    def __init__(self) -> None:
        self._vectors_by_file_id: dict[str, list[np.ndarray]] = {}
        self._chunks_by_file_id: dict[str, list[ChunkRecord]] = {}
        self._tokens_by_file_id: dict[str, list[set[str]]] = {}
        self._matrix_by_file_id: dict[str, np.ndarray] = {}

    def upsert_file_chunks(self, file_id: str, chunks: list[ChunkRecord], vectors: list[np.ndarray]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors count mismatch")
        self._chunks_by_file_id[file_id] = chunks
        self._vectors_by_file_id[file_id] = vectors
        self._tokens_by_file_id[file_id] = [self._tokenize(chunk.text) for chunk in chunks]
        if vectors:
            self._matrix_by_file_id[file_id] = np.vstack(vectors)
        else:
            self._matrix_by_file_id[file_id] = np.empty((0, 0), dtype=np.float32)

    def search(self, query_vector: np.ndarray, top_k: int = 5, file_id: str | None = None) -> list[VectorMatch]:
        candidates: list[tuple[np.ndarray, ChunkRecord]] = []
        if file_id:
            for vector, chunk in zip(
                self._vectors_by_file_id.get(file_id, []),
                self._chunks_by_file_id.get(file_id, []),
                strict=False,
            ):
                candidates.append((vector, chunk))
        else:
            for current_file_id, vectors in self._vectors_by_file_id.items():
                chunks = self._chunks_by_file_id.get(current_file_id, [])
                for vector, chunk in zip(vectors, chunks, strict=False):
                    candidates.append((vector, chunk))

        scored: list[VectorMatch] = []
        for vector, chunk in candidates:
            score = float(np.dot(query_vector, vector))
            scored.append(VectorMatch(score=score, chunk=chunk))

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]

    def all_items(self, file_id: str | None = None) -> list[tuple[np.ndarray, ChunkRecord]]:
        candidates: list[tuple[np.ndarray, ChunkRecord]] = []
        if file_id:
            for vector, chunk in zip(
                self._vectors_by_file_id.get(file_id, []),
                self._chunks_by_file_id.get(file_id, []),
                strict=False,
            ):
                candidates.append((vector, chunk))
            return candidates

        for current_file_id, vectors in self._vectors_by_file_id.items():
            chunks = self._chunks_by_file_id.get(current_file_id, [])
            for vector, chunk in zip(vectors, chunks, strict=False):
                candidates.append((vector, chunk))
        return candidates

    def semantic_candidates(
        self,
        query_vector: np.ndarray,
        limit: int,
    ) -> list[tuple[float, ChunkRecord, set[str]]]:
        candidates: list[tuple[float, ChunkRecord, set[str]]] = []
        if limit <= 0:
            return candidates

        for file_id, matrix in self._matrix_by_file_id.items():
            if matrix.size == 0:
                continue

            scores = matrix @ query_vector
            if scores.size == 0:
                continue

            top_n = min(limit, scores.shape[0])
            top_indices = np.argpartition(scores, -top_n)[-top_n:]
            sorted_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

            chunks = self._chunks_by_file_id.get(file_id, [])
            token_sets = self._tokens_by_file_id.get(file_id, [])
            for index in sorted_indices:
                idx = int(index)
                if idx >= len(chunks):
                    continue
                tokens = token_sets[idx] if idx < len(token_sets) else self._tokenize(chunks[idx].text)
                candidates.append((float(scores[idx]), chunks[idx], tokens))

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[:limit]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(word for word in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in text).split() if len(word) >= 3)


vector_store = InMemoryVectorStore()
