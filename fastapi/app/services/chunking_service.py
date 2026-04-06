from dataclasses import dataclass
import re
from uuid import uuid4

from app.core.config import settings


@dataclass
class ChunkRecord:
    chunk_id: str
    file_id: str
    chunk_index: int
    page_start: int
    page_end: int
    text: str
    start_offset: int
    end_offset: int


class ChunkingService:
    def split_pages(self, file_id: str, pages: list[tuple[int, str]]) -> list[ChunkRecord]:
        chunk_size = settings.chunk_size
        chunk_overlap = settings.chunk_overlap
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")

        chunks: list[ChunkRecord] = []
        all_sentences = self._collect_sentences(pages)
        if not all_sentences:
            return chunks

        chunk_index = 0
        current: list[dict[str, int | str]] = []
        current_len = 0
        current_concept = "general"

        for sentence in all_sentences:
            sentence_text = str(sentence["text"])
            sentence_len = len(sentence_text)
            sentence_concept = str(sentence.get("concept", "general"))

            concept_switched = (
                current
                and current_concept != "general"
                and sentence_concept != "general"
                and current_concept != sentence_concept
            )
            if concept_switched:
                chunks.append(self._build_chunk(file_id, chunk_index, current))
                chunk_index += 1
                current = []
                current_len = 0
                current_concept = sentence_concept

            if current and current_len + 1 + sentence_len > chunk_size:
                chunks.append(self._build_chunk(file_id, chunk_index, current))
                chunk_index += 1

                current = self._overlap_tail(current, chunk_overlap, current_concept)
                current_len = sum(len(str(item["text"])) for item in current)

            current.append(sentence)
            current_len = current_len + sentence_len if current_len == 0 else current_len + 1 + sentence_len
            if current_concept == "general":
                current_concept = sentence_concept

        if current:
            chunks.append(self._build_chunk(file_id, chunk_index, current))

        return chunks

    @staticmethod
    def _build_chunk(
        file_id: str,
        chunk_index: int,
        sentences: list[dict[str, int | str]],
    ) -> ChunkRecord:
        text = " ".join(str(item["text"]).strip() for item in sentences if str(item["text"]).strip())
        first = sentences[0]
        last = sentences[-1]
        return ChunkRecord(
            chunk_id=str(uuid4()),
            file_id=file_id,
            chunk_index=chunk_index,
            page_start=int(first["page_number"]),
            page_end=int(last["page_number"]),
            text=text,
            start_offset=int(first["start_offset"]),
            end_offset=int(last["end_offset"]),
        )

    @staticmethod
    def _collect_sentences(pages: list[tuple[int, str]]) -> list[dict[str, int | str]]:
        sentence_pattern = re.compile(r"[^.!?]+[.!?]?")
        sentences: list[dict[str, int | str]] = []
        global_offset = 0

        for page_number, page_text in pages:
            normalized = " ".join(page_text.split())
            for match in sentence_pattern.finditer(normalized):
                sentence = match.group(0).strip()
                if len(sentence) < 2:
                    continue
                if ChunkingService._is_noisy_sentence(sentence):
                    continue
                start = match.start()
                end = match.end()
                sentences.append(
                    {
                        "page_number": page_number,
                        "text": sentence,
                        "concept": ChunkingService._detect_concept(sentence),
                        "start_offset": global_offset + start,
                        "end_offset": global_offset + end,
                    }
                )
            global_offset += len(normalized) + 1

        return sentences

    @staticmethod
    def _overlap_tail(
        sentences: list[dict[str, int | str]],
        chunk_overlap: int,
        concept: str,
    ) -> list[dict[str, int | str]]:
        if not sentences or chunk_overlap <= 0:
            return []

        kept: list[dict[str, int | str]] = []
        kept_len = 0
        for item in reversed(sentences):
            item_concept = str(item.get("concept", "general"))
            if concept != "general" and item_concept not in {concept, "general"}:
                break

            text_len = len(str(item["text"]))
            next_len = text_len if kept_len == 0 else kept_len + 1 + text_len
            if next_len > chunk_overlap and kept:
                break
            kept.append(item)
            kept_len = next_len
            if kept_len >= chunk_overlap:
                break

        kept.reverse()
        return kept

    @staticmethod
    def _is_noisy_sentence(sentence: str) -> bool:
        s = " ".join(sentence.split()).strip()
        lower = s.lower()
        if len(s) < 20:
            return True
        if re.match(r"^(figure|fig\.|table)\s+\d+", lower):
            return True
        if re.match(r"^(activity|think and reflect)\b", lower):
            return True
        if re.search(r"\b(think and reflect|activity)\b", lower):
            return True
        if re.match(r"^[a-z]\)\s", lower):
            return True
        if re.match(r"^[\d\.\-\s]+$", lower):
            return True
        return False

    @staticmethod
    def _detect_concept(sentence: str) -> str:
        s = sentence.lower()
        concept_keywords: dict[str, tuple[str, ...]] = {
            "machine_learning": ("machine learning", "supervised", "unsupervised", "reinforcement learning"),
            "nlp": ("natural language processing", "nlp", "text mining", "tokenization", "sentiment"),
            "computer_vision": ("computer vision", "image", "object detection", "face recognition"),
            "deep_learning": ("deep learning", "neural network", "cnn", "rnn", "transformer"),
            "iot": ("internet of things", "iot", "sensor", "smart device"),
            "blockchain": ("blockchain", "distributed ledger", "crypto", "smart contract"),
        }

        best_concept = "general"
        best_score = 0
        for concept, keywords in concept_keywords.items():
            score = sum(1 for kw in keywords if kw in s)
            if score > best_score:
                best_score = score
                best_concept = concept
        return best_concept
