from pathlib import Path
import re
from typing import List, Tuple
from pypdf import PdfReader


class TextExtractionService:

    def extract_pages(self, file_path: str) -> List[Tuple[int, str]]:
        reader = PdfReader(file_path)
        pages = []

        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            text = self._quick_clean(text)

            if text:
                pages.append((i, text))

        return pages

    def build_chunks(self, pages, chunk_size=400, overlap=50):
        chunks = []

        for page, text in pages:
            words = text.split()   # ⚡ fast instead of sentences

            i = 0
            while i < len(words):
                chunk_words = words[i:i + chunk_size]
                chunk_text = " ".join(chunk_words)

                # quick noise filter
                if not self._is_noise(chunk_text):
                    chunks.append({
                        "text": chunk_text,
                        "page": page
                    })

                i += (chunk_size - overlap)

        return chunks

    # ------------------------
    # FAST CLEANING
    # ------------------------

    def _quick_clean(self, text: str) -> str:
        text = text.replace("\n", " ")
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _is_noise(self, text: str) -> bool:
        lower = text.lower()

        if "figure" in lower or "activity" in lower:
            return True
        if "think and reflect" in lower:
            return True

        return False