import re
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import StrEnum

from app.core.config import settings
from app.services.chunking_service import ChunkRecord
from app.services.embedding_service import EmbeddingService
from app.services.vector_store_service import vector_store

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


@dataclass
class RetrievedMatch:
    score: float
    semantic_score: float
    lexical_score: float
    chunk: ChunkRecord
    tokens: set[str]


class QueryIntent(StrEnum):
    DEFINITION = "definition"
    SUMMARY = "summary"
    LIST = "list"
    COMPARE = "compare"
    GENERAL = "general"


class RagService:
    def __init__(self) -> None:
        self._embedding_service = EmbeddingService()
        self._openai_client = None
        self._ollama_endpoint: str | None = None
        self._answer_cache: dict[tuple[str, str, str], tuple[float, str, int]] = {}
        if (
            settings.llm_provider.lower() == "openai"
            and settings.openai_chat_enabled
            and settings.openai_api_key
            and OpenAI is not None
        ):
            self._openai_client = OpenAI(api_key=settings.openai_api_key)

    def answer(self, query: str) -> tuple[str, int]:
        normalized_query = self._normalize_query_for_retrieval(query)
        cache_key = (
            settings.llm_provider.lower().strip(),
            normalized_query.lower(),
            str(vector_store.cache_version()),
        )
        cache_ttl = max(0, int(settings.rag_answer_cache_ttl_seconds))
        now = time.time()
        if cache_ttl > 0:
            cached = self._answer_cache.get(cache_key)
            if cached and (now - cached[0]) <= cache_ttl:
                return cached[1], cached[2]

        intent = self._detect_intent(normalized_query)

        query_vector = self._embedding_service.embed_query(normalized_query)
        matches = self._hybrid_search(
            query=normalized_query,
            query_vector=query_vector,
            top_k=settings.retrieval_top_k,
        )
        matches = self._deduplicate_matches(matches)
        matches = self._filter_noise_by_content(matches)

        if not matches:
            return ("No indexed content found yet. Upload and process files before querying.", 0)

        sources: list[dict[str, object]] = []
        for match in matches:
            sources.append(
                {
                    "file_id": match.chunk.file_id,
                    "chunk_id": match.chunk.chunk_id,
                    "page_start": match.chunk.page_start,
                    "page_end": match.chunk.page_end,
                    "score": round(match.score, 4),
                    "snippet": match.chunk.text[:220],
                    "full_text": match.chunk.text,
                }
            )

        answer = self._generate_answer(query=normalized_query, sources=sources, intent=intent)
        source_count = len(sources)
        if cache_ttl > 0:
            self._answer_cache[cache_key] = (now, answer, source_count)
            if len(self._answer_cache) > 200:
                oldest_key = min(self._answer_cache, key=lambda key: self._answer_cache[key][0])
                self._answer_cache.pop(oldest_key, None)
        return answer, source_count

    def _hybrid_search(self, query: str, query_vector, top_k: int) -> list[RetrievedMatch]:
        query_tokens = self._tokenize(query)
        raw_query = query.lower().strip()
        semantic_limit = max(
            top_k * settings.retrieval_candidate_multiplier,
            settings.retrieval_semantic_pool,
        )
        semantic_candidates = vector_store.semantic_candidates(query_vector=query_vector, limit=semantic_limit)
        lexical_candidates = vector_store.lexical_candidates(
            query_tokens=query_tokens,
            raw_query=raw_query,
            limit=semantic_limit,
        )
        candidates = semantic_candidates + lexical_candidates
        scored: list[RetrievedMatch] = []

        for semantic_score, chunk, chunk_tokens in candidates:
            lexical_score = self._keyword_search_score(query_tokens, chunk.text, raw_query)
            final_score = (0.62 * semantic_score) + (0.38 * lexical_score)
            scored.append(
                RetrievedMatch(
                    score=final_score,
                    semantic_score=semantic_score,
                    lexical_score=lexical_score,
                    chunk=chunk,
                    tokens=chunk_tokens,
                )
            )

        if not scored:
            return []

        scored = self._filter_noisy_matches(scored)
        if not scored:
            return []

        scored = self._rerank_matches(scored, query_tokens=query_tokens, raw_query=raw_query)
        max_candidates = max(top_k * settings.retrieval_candidate_multiplier, top_k)
        scored = scored[:max_candidates]
        return self._apply_diversity(scored, top_k=top_k)

    def _generate_answer(self, query: str, sources: list[dict[str, object]], intent: QueryIntent) -> str:
        llm_answer = self._build_answer_with_provider(query=query, sources=sources, intent=intent)
        if llm_answer:
            return llm_answer
        if settings.llm_answer_required:
            return (
                "LLM answer generation is required but not available. "
                "Set provider config correctly (LLM_PROVIDER and related keys/service), then restart FastAPI."
            )
        return self._build_answer_local(query=query, sources=sources, intent=intent)

    def _build_answer_with_provider(
        self,
        query: str,
        sources: list[dict[str, object]],
        intent: QueryIntent,
    ) -> str | None:
        provider = settings.llm_provider.lower().strip()
        if provider == "openai":
            return self._build_answer_openai(query=query, sources=sources, intent=intent)
        if provider == "ollama":
            return self._build_answer_ollama(query=query, sources=sources, intent=intent)
        if provider in {"huggingface", "hf"}:
            return self._build_answer_huggingface(query=query, sources=sources, intent=intent)
        return f"LLM provider not supported: {settings.llm_provider}"

    def _build_answer_openai(
        self,
        query: str,
        sources: list[dict[str, object]],
        intent: QueryIntent,
    ) -> str | None:
        if self._openai_client is None:
            return None

        context_lines = []
        for source in sources[:5]:
            page_label = f"{source['page_start']}"
            if source["page_end"] != source["page_start"]:
                page_label = f"{source['page_start']}-{source['page_end']}"
            context_lines.append(f"[Page {page_label}] {source['full_text']}")
        context = "\n".join(context_lines)

        intent_instruction = {
            QueryIntent.DEFINITION: "Return a direct definition in 1-3 sentences.",
            QueryIntent.SUMMARY: "Return a concise summary in 4-6 bullet points.",
            QueryIntent.LIST: "Return a clean numbered list.",
            QueryIntent.COMPARE: "Return a brief side-by-side comparison.",
            QueryIntent.GENERAL: "Return a concise direct answer.",
        }[intent]

        try:
            completion = self._openai_client.chat.completions.create(
                model=settings.openai_chat_model,
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful assistant. Answer in plain, human-readable language.\n"
                            "Use only the provided context.\n"
                            "If context is insufficient, say so clearly."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Question: {query}\n\n"
                            f"Context chunks:\n{context}\n\n"
                            f"{intent_instruction}\n"
                            "Do not include chunk ids or implementation details."
                        ),
                    },
                ],
            )
            return (completion.choices[0].message.content or "").strip() or None
        except Exception as ex:
            if settings.llm_answer_required:
                return f"LLM call failed: {ex.__class__.__name__}: {str(ex)}"
            return None

    def _build_answer_ollama(
        self,
        query: str,
        sources: list[dict[str, object]],
        intent: QueryIntent,
    ) -> str | None:
        context = self._build_context_text(sources)
        intent_instruction = self._intent_instruction(intent)
        base_url = settings.ollama_base_url.rstrip("/")
        timeout_seconds = max(5, int(settings.ollama_timeout_seconds))
        max_tokens = max(32, int(settings.ollama_max_output_tokens))

        system_message = (
            "You are a helpful assistant. Use only provided context. "
            "If context is insufficient, say so clearly."
        )

        def _prompt_for(ctx: str) -> str:
            return (
                f"Question: {query}\n\n"
                f"Context chunks:\n{ctx}\n\n"
                f"{intent_instruction}\n"
                "Return a concise final answer only."
            )

        def _post_json(url: str, payload: dict, request_timeout: int) -> dict:
            request = urllib.request.Request(
                url=url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        def _call_endpoint(endpoint: str, prompt_text: str, tokens: int, request_timeout: int) -> str | None:
            if endpoint == "/api/chat":
                payload = {
                    "model": settings.ollama_chat_model,
                    "stream": False,
                    "keep_alive": settings.ollama_keep_alive,
                    "options": {"temperature": 0.2, "num_predict": tokens},
                    "messages": [
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": prompt_text},
                    ],
                }
                body = _post_json(base_url + endpoint, payload, request_timeout)
                return str(body.get("message", {}).get("content", "")).strip() or None

            payload = {
                "model": settings.ollama_chat_model,
                "stream": False,
                "keep_alive": settings.ollama_keep_alive,
                "options": {"temperature": 0.2, "num_predict": tokens},
                "prompt": f"{system_message}\n\n{prompt_text}",
            }
            body = _post_json(base_url + endpoint, payload, request_timeout)
            return str(body.get("response", "")).strip() or None

        endpoints = ["/api/chat", "/api/generate"]
        if self._ollama_endpoint in endpoints:
            endpoints = [self._ollama_endpoint] + [ep for ep in endpoints if ep != self._ollama_endpoint]

        timeout_seen = False
        timeout_detail = "timed out"

        for endpoint in endpoints:
            try:
                text = _call_endpoint(
                    endpoint=endpoint,
                    prompt_text=_prompt_for(context),
                    tokens=max_tokens,
                    request_timeout=timeout_seconds,
                )
                if text:
                    self._ollama_endpoint = endpoint
                    return text
            except urllib.error.HTTPError as ex:
                if ex.code == 404:
                    continue
                error_body = ex.read().decode("utf-8", errors="ignore")
                if settings.llm_answer_required:
                    return f"LLM call failed: HTTPError {ex.code}: {error_body}"
                return None
            except Exception as ex:
                message = str(ex).lower()
                if isinstance(ex, TimeoutError) or "timed out" in message:
                    timeout_seen = True
                    timeout_detail = str(ex)
                    continue
                if settings.llm_answer_required:
                    return f"LLM call failed: {ex.__class__.__name__}: {str(ex)}"
                return None

        if timeout_seen:
            # Retry once with compact context and smaller output for slow local models.
            compact_context = self._build_context_text(sources[:1])
            retry_timeout = max(timeout_seconds + 20, 40)
            retry_tokens = min(max_tokens, 80)
            for endpoint in endpoints:
                try:
                    text = _call_endpoint(
                        endpoint=endpoint,
                        prompt_text=_prompt_for(compact_context),
                        tokens=retry_tokens,
                        request_timeout=retry_timeout,
                    )
                    if text:
                        self._ollama_endpoint = endpoint
                        return text
                except urllib.error.HTTPError:
                    continue
                except Exception:
                    continue
            if settings.llm_answer_required:
                return (
                    "LLM call failed: TimeoutError: timed out. "
                    "Try increasing OLLAMA_TIMEOUT_SECONDS to 45-60 or use a smaller model."
                )
            return None

        return None

    def _build_answer_huggingface(
        self,
        query: str,
        sources: list[dict[str, object]],
        intent: QueryIntent,
    ) -> str | None:
        if not settings.hf_api_token:
            if settings.llm_answer_required:
                return "LLM call failed: HuggingFace token is missing (HF_API_TOKEN)."
            return None

        context = self._build_context_text(sources)
        prompt = (
            "You are a helpful assistant. Use only provided context.\n"
            f"Instruction: {self._intent_instruction(intent)}\n\n"
            f"Question: {query}\n\n"
            f"Context:\n{context}\n\n"
            "Answer:"
        )
        url = f"https://api-inference.huggingface.co/models/{settings.hf_model}"
        payload = {"inputs": prompt, "parameters": {"max_new_tokens": 220, "temperature": 0.2}}
        request = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.hf_api_token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))

            if isinstance(body, list) and body:
                generated = body[0].get("generated_text", "")
                text = str(generated).strip()
                if "Answer:" in text:
                    text = text.split("Answer:", 1)[-1].strip()
                return text or None
            if isinstance(body, dict) and "generated_text" in body:
                return str(body["generated_text"]).strip() or None
            return None
        except urllib.error.HTTPError as ex:
            error_body = ex.read().decode("utf-8", errors="ignore")
            if settings.llm_answer_required:
                return f"LLM call failed: HTTPError {ex.code}: {error_body}"
            return None
        except Exception as ex:
            if settings.llm_answer_required:
                return f"LLM call failed: {ex.__class__.__name__}: {str(ex)}"
            return None

    @staticmethod
    def _intent_instruction(intent: QueryIntent) -> str:
        return {
            QueryIntent.DEFINITION: "Return a direct definition in 1-3 sentences.",
            QueryIntent.SUMMARY: "Return a concise summary in 4-6 bullet points.",
            QueryIntent.LIST: "Return a clean numbered list.",
            QueryIntent.COMPARE: "Return a brief side-by-side comparison.",
            QueryIntent.GENERAL: "Return a concise direct answer.",
        }[intent]

    @staticmethod
    def _build_context_text(sources: list[dict[str, object]]) -> str:
        lines = []
        chunk_count = max(1, int(settings.llm_context_chunks))
        char_limit = max(200, int(settings.llm_chunk_char_limit))
        for source in sources[:chunk_count]:
            page_label = f"{source['page_start']}"
            if source["page_end"] != source["page_start"]:
                page_label = f"{source['page_start']}-{source['page_end']}"
            full_text = str(source["full_text"]).strip()
            compact = re.sub(r"\s+", " ", full_text)
            lines.append(f"[Page {page_label}] {compact[:char_limit]}")
        return "\n".join(lines)

    @staticmethod
    def _build_answer_local(query: str, sources: list[dict[str, object]], intent: QueryIntent) -> str:
        top_texts = [str(source["full_text"]) for source in sources[:5]]

        if intent == QueryIntent.DEFINITION:
            definition_answer = RagService._definition_style_answer(query=query, snippets=top_texts)
            if definition_answer:
                return definition_answer

        top_sentences = RagService._extract_top_sentences(query=query, snippets=top_texts, limit=3)
        if not top_sentences:
            return "I could not find a confident answer in the indexed content."

        if intent == QueryIntent.LIST:
            return "\n".join(f"{idx}. {sentence}" for idx, sentence in enumerate(top_sentences, start=1))

        if intent == QueryIntent.SUMMARY:
            return "\n".join(f"- {sentence}" for sentence in top_sentences)

        return " ".join(top_sentences[:2])

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]{3,}", text.lower()))

    @staticmethod
    def _lexical_overlap_score(query_tokens: set[str], candidate_tokens: set[str]) -> float:
        if not query_tokens or not candidate_tokens:
            return 0.0
        overlap = len(query_tokens.intersection(candidate_tokens))
        return overlap / len(query_tokens)

    @staticmethod
    def _keyword_search_score(query_tokens: set[str], chunk_text: str, raw_query: str) -> float:
        candidate_tokens = RagService._tokenize(chunk_text)
        overlap_score = RagService._lexical_overlap_score(query_tokens, candidate_tokens)

        chunk_lower = chunk_text.lower()
        phrase_bonus = 0.15 if raw_query in chunk_lower and len(raw_query) > 8 else 0.0

        term_hits = 0
        for token in query_tokens:
            if token in chunk_lower:
                term_hits += chunk_lower.count(token)
        density_bonus = min(term_hits / max(len(query_tokens), 1), 1.0) * 0.2

        return min(overlap_score + phrase_bonus + density_bonus, 1.0)

    @staticmethod
    def _extract_top_sentences(query: str, snippets: list[str], limit: int = 3) -> list[str]:
        query_tokens = RagService._tokenize(query)
        sentences: list[tuple[float, str]] = []

        for snippet in snippets:
            cleaned_snippet = RagService._clean_text(snippet)
            parts = re.split(r"(?<=[.!?])\s+", cleaned_snippet)
            for part in parts:
                cleaned = part.strip()
                if len(cleaned) < 25:
                    continue
                if RagService._is_noise_sentence(cleaned):
                    continue
                score = RagService._lexical_overlap_score(query_tokens, RagService._tokenize(cleaned))
                if score > 0:
                    sentences.append((score, cleaned))

        sentences.sort(key=lambda item: item[0], reverse=True)
        return [sentence for _, sentence in sentences[:limit]]

    @staticmethod
    def _definition_style_answer(query: str, snippets: list[str]) -> str | None:
        concept = RagService._extract_concept_from_query(query)
        if not concept:
            return None

        concept_tokens = RagService._tokenize(concept)
        if not concept_tokens:
            return None

        best_sentence = None
        best_score = 0.0
        concept_lower = concept.lower().strip()

        for snippet in snippets:
            cleaned_snippet = RagService._clean_text(snippet)
            parts = re.split(r"(?<=[.!?])\s+", cleaned_snippet)
            for part in parts:
                sentence = part.strip()
                if len(sentence) < 25:
                    continue
                if RagService._is_noise_sentence(sentence):
                    continue

                sentence_tokens = RagService._tokenize(sentence)
                score = RagService._lexical_overlap_score(concept_tokens, sentence_tokens)
                sentence_lower = sentence.lower()

                if f"{concept_lower} is" in sentence_lower:
                    score += 0.45
                elif concept_lower in sentence_lower:
                    score += 0.15
                if " is " in sentence_lower:
                    score += 0.1

                if score > best_score:
                    best_score = score
                    best_sentence = sentence

        if best_sentence and best_score >= 0.65:
            cleaned = RagService._clean_definition_sentence(best_sentence, concept)
            return f"According to the document, {cleaned}"
        return None

    @staticmethod
    def _extract_concept_from_query(query: str) -> str | None:
        normalized = " ".join(query.strip().split()).lower()
        match = re.search(r"what is (.+?)(?:\?|$)", normalized)
        if match:
            concept = match.group(1).strip()
            concept = re.sub(
                r"\b(mentioned in the uploaded document|in the uploaded document|from the document)\b",
                "",
                concept,
            ).strip()
            concept = re.sub(r"^(the|a|an)\s+", "", concept).strip()
            return concept
        return None

    @staticmethod
    def _clean_text(text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text)
        cleaned = re.sub(r"\b([a-z])\s+([A-Z])\b", r"\1\2", cleaned)
        return cleaned.strip()

    @staticmethod
    def _clean_definition_sentence(sentence: str, concept: str) -> str:
        cleaned = RagService._clean_text(sentence)
        cleaned = re.sub(r"^\d+(?:\.\d+)*\s+", "", cleaned)
        cleaned = re.sub(r"^[a-zA-Z]\)\s*", "", cleaned)
        cleaned = re.sub(r"^\(?[ivxIVX]+\)\s*", "", cleaned)

        concept_escaped = re.escape(concept.strip())
        cleaned = re.sub(
            rf"^({concept_escaped})\s+({concept_escaped})\b",
            r"\1",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(r"\s+\w{1,3}$", "", cleaned)
        cleaned = cleaned.strip(" -,:;")
        cleaned = re.sub(r"\s+", " ", cleaned)

        if cleaned and cleaned[-1] not in ".!?":
            cleaned = f"{cleaned}."
        return cleaned

    @staticmethod
    def _normalize_query_for_retrieval(query: str) -> str:
        normalized = " ".join(query.strip().split())
        normalized = re.sub(
            r"\b(mentioned in the uploaded document|in the uploaded document|from the uploaded document)\b",
            "",
            normalized,
            flags=re.IGNORECASE,
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _is_noise_sentence(sentence: str) -> bool:
        s = sentence.strip()
        lower = s.lower()

        if len(s) < 25:
            return True
        if re.match(r"^(notes?|summary|contents?)\b", lower):
            return True
        if re.match(r"^[a-z]\)\s", lower):
            return True
        if re.match(r"^\d+\s*$", lower):
            return True
        if re.match(r"^[-*]\s", lower):
            return True
        if re.match(r"^[\d\.\-\s]+$", lower):
            return True
        if "chapter" in lower and "machine learning" not in lower:
            return True
        if re.search(r"\b(page|index|contents?)\b", lower):
            return True

        alpha_chars = sum(ch.isalpha() for ch in s)
        if alpha_chars / max(len(s), 1) < 0.55:
            return True
        return False

    def _deduplicate_matches(self, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        deduped: list[RetrievedMatch] = []
        seen_ids: set[str] = set()
        seen_token_sets: list[set[str]] = []

        for match in matches:
            chunk_id = match.chunk.chunk_id
            if chunk_id in seen_ids:
                continue

            tokens = match.tokens
            if not tokens:
                continue

            is_duplicate = False
            for prev_tokens in seen_token_sets:
                similarity = self._jaccard(tokens, prev_tokens)
                if similarity >= 0.85:
                    is_duplicate = True
                    break

            if is_duplicate:
                continue

            seen_ids.add(chunk_id)
            seen_token_sets.append(tokens)
            deduped.append(match)

        return deduped

    def _filter_noisy_matches(self, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        filtered: list[RetrievedMatch] = []
        for match in matches:
            if (
                match.semantic_score < settings.retrieval_min_semantic_score
                and match.lexical_score < settings.retrieval_min_lexical_score
            ):
                continue
            filtered.append(match)
        return filtered

    def _filter_noise_by_content(self, matches: list[RetrievedMatch]) -> list[RetrievedMatch]:
        filtered: list[RetrievedMatch] = []
        for match in matches:
            text = self._clean_text(match.chunk.text)
            if len(text) < 60:
                continue
            if self._is_noise_sentence(text[:220]):
                continue
            filtered.append(match)

        return filtered if filtered else matches[: max(1, settings.retrieval_top_k // 2)]

    def _rerank_matches(
        self,
        matches: list[RetrievedMatch],
        query_tokens: set[str],
        raw_query: str,
    ) -> list[RetrievedMatch]:
        reranked: list[RetrievedMatch] = []
        for match in matches:
            phrase_boost = 0.1 if raw_query and raw_query in match.chunk.text.lower() else 0.0
            coverage = self._lexical_overlap_score(query_tokens, match.tokens)
            rerank_score = (0.7 * match.score) + (0.2 * coverage) + phrase_boost
            reranked.append(
                RetrievedMatch(
                    score=rerank_score,
                    semantic_score=match.semantic_score,
                    lexical_score=match.lexical_score,
                    chunk=match.chunk,
                    tokens=match.tokens,
                )
            )

        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked

    def _apply_diversity(self, matches: list[RetrievedMatch], top_k: int) -> list[RetrievedMatch]:
        selected: list[RetrievedMatch] = []
        for candidate in matches:
            if len(selected) >= top_k:
                break

            too_similar = False
            for chosen in selected:
                similarity = self._jaccard(candidate.tokens, chosen.tokens)
                if similarity >= settings.retrieval_max_jaccard_similarity:
                    too_similar = True
                    break

            if too_similar:
                continue
            selected.append(candidate)

        return selected

    @staticmethod
    def _detect_intent(query: str) -> QueryIntent:
        q = query.lower().strip()
        if q.startswith("what is ") or q.startswith("define "):
            return QueryIntent.DEFINITION
        if any(k in q for k in ["summarize", "summary", "in short", "briefly explain"]):
            return QueryIntent.SUMMARY
        if any(k in q for k in ["list ", "types of", "kinds of", "examples of"]):
            return QueryIntent.LIST
        if any(k in q for k in ["difference between", "compare", "vs ", "versus"]):
            return QueryIntent.COMPARE
        return QueryIntent.GENERAL

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a or not b:
            return 0.0
        intersection = len(a.intersection(b))
        union = len(a.union(b))
        if union == 0:
            return 0.0
        return intersection / union

