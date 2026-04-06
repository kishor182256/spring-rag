from __future__ import annotations

import pickle
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.services.chunking_service import ChunkRecord

try:
    import faiss  # type: ignore
except Exception:  # pragma: no cover
    faiss = None


@dataclass
class VectorMatch:
    score: float
    chunk: ChunkRecord


class PersistentVectorStore:
    def __init__(self) -> None:
        self._store_dir = Path(settings.vector_store_dir)
        self._store_dir.mkdir(parents=True, exist_ok=True)

        self._index_path = self._store_dir / 'faiss.index'
        self._state_path = self._store_dir / 'vector_state.pkl'

        self._vectors_by_file_id: dict[str, np.ndarray] = {}
        self._chunks_by_file_id: dict[str, list[ChunkRecord]] = {}
        self._tokens_by_file_id: dict[str, list[set[str]]] = {}

        self._flat_chunks: list[ChunkRecord] = []
        self._flat_tokens: list[set[str]] = []

        self._dimension: int = 0
        self._index: Any | None = None
        self._version: int = 0

        self._load_from_disk()

    def upsert_file_chunks(self, file_id: str, chunks: list[ChunkRecord], vectors: list[np.ndarray]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError('chunks and vectors count mismatch')

        if not chunks:
            self._vectors_by_file_id[file_id] = np.empty((0, 0), dtype=np.float32)
            self._chunks_by_file_id[file_id] = []
            self._tokens_by_file_id[file_id] = []
            self._rebuild_index_and_save()
            return

        matrix = np.vstack([np.asarray(vector, dtype=np.float32) for vector in vectors]).astype(np.float32)
        self._vectors_by_file_id[file_id] = matrix
        self._chunks_by_file_id[file_id] = chunks
        self._tokens_by_file_id[file_id] = [self._tokenize(chunk.text) for chunk in chunks]

        self._rebuild_index_and_save()
        self._version += 1

    def list_indexed_file_ids(self) -> list[str]:
        return sorted([file_id for file_id, chunks in self._chunks_by_file_id.items() if chunks])

    def get_chunks(self, file_id: str) -> list[ChunkRecord]:
        return list(self._chunks_by_file_id.get(file_id, []))

    def has_file(self, file_id: str) -> bool:
        return file_id in self._chunks_by_file_id and len(self._chunks_by_file_id[file_id]) > 0

    def cache_version(self) -> int:
        return self._version

    def semantic_candidates(
        self,
        query_vector: np.ndarray,
        limit: int,
    ) -> list[tuple[float, ChunkRecord, set[str]]]:
        if limit <= 0:
            return []
        if not self._flat_chunks:
            return []

        query = np.asarray(query_vector, dtype=np.float32).reshape(1, -1)

        # FAISS path (preferred)
        if self._index is not None:
            top_k = min(limit, len(self._flat_chunks))
            scores, indices = self._index.search(query, top_k)
            result: list[tuple[float, ChunkRecord, set[str]]] = []
            for score, idx in zip(scores[0], indices[0], strict=False):
                i = int(idx)
                if i < 0 or i >= len(self._flat_chunks):
                    continue
                result.append((float(score), self._flat_chunks[i], self._flat_tokens[i]))
            return result

        # Fallback path if faiss is unavailable.
        all_vectors = []
        for matrix in self._vectors_by_file_id.values():
            if matrix.size > 0:
                all_vectors.append(matrix)
        if not all_vectors:
            return []

        full_matrix = np.vstack(all_vectors)
        scores = (full_matrix @ query.reshape(-1)).astype(np.float32)
        top_k = min(limit, scores.shape[0])
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        sorted_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        result = []
        for idx in sorted_indices:
            i = int(idx)
            result.append((float(scores[i]), self._flat_chunks[i], self._flat_tokens[i]))
        return result

    def lexical_candidates(
        self,
        query_tokens: set[str],
        raw_query: str,
        limit: int,
    ) -> list[tuple[float, ChunkRecord, set[str]]]:
        if limit <= 0 or not query_tokens or not self._flat_chunks:
            return []

        scored: list[tuple[float, ChunkRecord, set[str]]] = []
        for chunk, tokens in zip(self._flat_chunks, self._flat_tokens, strict=False):
            overlap = len(query_tokens.intersection(tokens)) / max(len(query_tokens), 1)
            if overlap <= 0:
                continue

            text_lower = chunk.text.lower()
            phrase_bonus = 0.2 if raw_query and len(raw_query) > 8 and raw_query in text_lower else 0.0
            density_bonus = min(
                sum(text_lower.count(token) for token in query_tokens) / max(len(query_tokens), 1),
                1.0,
            ) * 0.2
            score = min(overlap + phrase_bonus + density_bonus, 1.0)
            scored.append((score, chunk, tokens))

        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[:limit]

    def _rebuild_index_and_save(self) -> None:
        self._flat_chunks = []
        self._flat_tokens = []
        matrices: list[np.ndarray] = []

        for file_id in sorted(self._chunks_by_file_id.keys()):
            chunks = self._chunks_by_file_id.get(file_id, [])
            vectors = self._vectors_by_file_id.get(file_id)
            tokens = self._tokens_by_file_id.get(file_id, [])

            if not chunks or vectors is None or vectors.size == 0:
                continue
            if vectors.shape[0] != len(chunks):
                continue

            if not tokens or len(tokens) != len(chunks):
                tokens = [self._tokenize(chunk.text) for chunk in chunks]
                self._tokens_by_file_id[file_id] = tokens

            matrices.append(vectors)
            self._flat_chunks.extend(chunks)
            self._flat_tokens.extend(tokens)

        self._index = None
        self._dimension = 0

        if matrices:
            full_matrix = np.vstack(matrices).astype(np.float32)
            self._dimension = int(full_matrix.shape[1])
            if faiss is not None:
                index = faiss.IndexFlatIP(self._dimension)
                index.add(full_matrix)
                self._index = index

        self._save_to_disk()

    def _save_to_disk(self) -> None:
        state = {
            'vectors_by_file_id': {
                file_id: matrix.astype(np.float32)
                for file_id, matrix in self._vectors_by_file_id.items()
            },
            'chunks_by_file_id': {
                file_id: [asdict(chunk) for chunk in chunks]
                for file_id, chunks in self._chunks_by_file_id.items()
            },
        }
        with self._state_path.open('wb') as file_handle:
            pickle.dump(state, file_handle)

        if self._index is not None and faiss is not None:
            faiss.write_index(self._index, str(self._index_path))

    def _load_from_disk(self) -> None:
        if not self._state_path.exists():
            return

        try:
            with self._state_path.open('rb') as file_handle:
                state = pickle.load(file_handle)

            raw_vectors: dict[str, np.ndarray] = state.get('vectors_by_file_id', {})
            raw_chunks: dict[str, list[dict[str, Any]]] = state.get('chunks_by_file_id', {})

            self._vectors_by_file_id = {
                file_id: np.asarray(matrix, dtype=np.float32)
                for file_id, matrix in raw_vectors.items()
            }
            self._chunks_by_file_id = {
                file_id: [ChunkRecord(**chunk_dict) for chunk_dict in chunk_dicts]
                for file_id, chunk_dicts in raw_chunks.items()
            }
            self._tokens_by_file_id = {
                file_id: [self._tokenize(chunk.text) for chunk in chunks]
                for file_id, chunks in self._chunks_by_file_id.items()
            }

            self._rebuild_flat_views()

            if faiss is not None and self._index_path.exists():
                try:
                    self._index = faiss.read_index(str(self._index_path))
                    self._dimension = int(self._index.d)
                except Exception:
                    self._rebuild_index_and_save()
            else:
                self._rebuild_index_and_save()

        except Exception:
            self._vectors_by_file_id = {}
            self._chunks_by_file_id = {}
            self._tokens_by_file_id = {}
            self._flat_chunks = []
            self._flat_tokens = []
            self._index = None
            self._dimension = 0

    def _rebuild_flat_views(self) -> None:
        self._flat_chunks = []
        self._flat_tokens = []
        for file_id in sorted(self._chunks_by_file_id.keys()):
            chunks = self._chunks_by_file_id.get(file_id, [])
            tokens = self._tokens_by_file_id.get(file_id, [])
            if not tokens or len(tokens) != len(chunks):
                tokens = [self._tokenize(chunk.text) for chunk in chunks]
                self._tokens_by_file_id[file_id] = tokens
            self._flat_chunks.extend(chunks)
            self._flat_tokens.extend(tokens)

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        cleaned = ''.join(ch.lower() if ch.isalnum() else ' ' for ch in text)
        return set(word for word in cleaned.split() if len(word) >= 3)


vector_store = PersistentVectorStore()
